import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..ai.decision import AIDecisionEngine
from ..api.market import PolymarketClient
from ..core.config import Config, CONTROL_FILE, PAPER_STATE_FILE
from ..core.state import StateManager, StatusExporter
from ..core.utils import load_trading_control, safe_float
from .executor import LiveExecutor, PaperExecutor

logger = logging.getLogger("trading_manager")


def _book_summary(book: Dict[str, Any], outcome_index: int) -> str:
    for outcome_book in book.get("outcomes", []):
        if outcome_book.get("index") != outcome_index:
            continue
        bids = (outcome_book.get("bids") or [])[:5]
        asks = (outcome_book.get("asks") or [])[:5]
        if bids or asks:
            return f"Bids(top5): {bids} | Asks(top5): {asks}"
    return "暂无深度数据"


def _build_ai_prompt(market: Dict[str, Any], book: Dict[str, Any]) -> str:
    outcome_lines = []
    book_lines = []
    for outcome in market.get("outcomes", []):
        label = outcome.get("label", f"Outcome {outcome.get('index', '?')}")
        price = outcome.get("price")
        best_bid = outcome.get("best_bid")
        best_ask = outcome.get("best_ask")
        outcome_lines.append(
            f"- [{outcome.get('index')}] {label}: 最新成交价 {price if price is not None else '--'}"
            f" | Bid {best_bid if best_bid is not None else '--'}"
            f" | Ask {best_ask if best_ask is not None else '--'}"
        )
        book_lines.append(f"- [{outcome.get('index')}] {label}: {_book_summary(book, outcome.get('index'))}")

    return (
        f"市场问题: {market.get('question', '?')}\n"
        f"市场 slug: {market.get('slug', '?')}\n"
        f"结束时间: {market.get('end_date', '?')}\n"
        f"可交易结果:\n" + "\n".join(outcome_lines) + "\n\n"
        f"订单簿深度:\n" + "\n".join(book_lines) + "\n\n"
        "请只在某一边存在明确优势、盘口可接受、且不是临近到期的情况下返回 BUY。\n"
        "如果优势不清楚、信息不足、或赔率/流动性不理想，请返回 SKIP。"
    )


def _merge_book_quotes(market: Dict[str, Any], book: Dict[str, Any]) -> None:
    by_index = {item.get("index"): item for item in book.get("outcomes", [])}
    for outcome in market.get("outcomes", []):
        book_item = by_index.get(outcome.get("index"))
        if not book_item:
            continue
        bids = book_item.get("bids") or []
        asks = book_item.get("asks") or []
        if bids:
            outcome["best_bid"] = safe_float(bids[0].get("price"), outcome.get("best_bid"))
        if asks:
            outcome["best_ask"] = safe_float(asks[0].get("price"), outcome.get("best_ask"))


class TradingBotManager:
    """Unified trading loop for paper/live execution."""

    def __init__(self):
        self.state_manager = StateManager(PAPER_STATE_FILE)
        self.market_api = PolymarketClient()
        self.ai_engine = AIDecisionEngine()

        self.current_mode = Config.get("TRADING_MODE", "paper").lower()
        self.executor = self._create_executor(self.current_mode)
        self.running = True

    def _create_executor(self, mode: str):
        if mode == "live":
            logger.info("🚀 初始化实盘执行引擎 (Live Mode)")
            return LiveExecutor(self.state_manager)
        logger.info("🧪 初始化模拟执行引擎 (Paper Mode)")
        return PaperExecutor(self.state_manager)

    async def check_mode_swap(self):
        new_mode = Config.get("TRADING_MODE", "paper").lower()
        if new_mode != self.current_mode:
            logger.warning("🔄 检测到模式变更: %s -> %s", self.current_mode, new_mode)
            if self.current_mode.startswith("paper") and new_mode == "live":
                logger.warning("🛡️ 模式切换安全响应: 丢弃模拟持仓")
                self.state_manager.update("positions", [])
                self.state_manager.update("orders", [])
            self.current_mode = new_mode
            self.executor = self._create_executor(new_mode)

    async def run_cycle(self):
        await self.check_mode_swap()
        control = load_trading_control(CONTROL_FILE)
        is_enabled = control.get("trading_enabled", True)
        now_utc = datetime.now(timezone.utc)

        base_status = {
            "running": True,
            "last_update": now_utc.isoformat(),
            "trading_mode": self.current_mode,
            "trading_enabled": is_enabled,
            "strategy_profile": Config.get("STRATEGY_PROFILE", "generic_binary"),
        }

        if not is_enabled:
            logger.info("⏸ 交易已在控制台关闭，本轮跳过执行")
            StatusExporter.export(base_status)
            return

        focus_market = await self.market_api.get_focus_market(now_utc)
        if not focus_market:
            logger.warning("⚠️ 未找到目标盘口，请先配置 TARGET_MARKET_SLUG / TARGET_MARKET_URL")
            StatusExporter.export({**base_status, "market_error": "未配置或无法解析目标市场"})
            return

        if not focus_market.get("binary") and not Config.get_bool("ALLOW_MULTI_OUTCOME", "false"):
            logger.warning("⚠️ 当前版本仅支持二元盘口: %s", focus_market.get("slug"))
            StatusExporter.export({
                **base_status,
                "market_slug": focus_market.get("slug", ""),
                "market_question": focus_market.get("question", ""),
                "market_end_date": focus_market.get("end_date", ""),
                "market_error": "当前版本仅支持二元盘口",
            })
            return

        book = await self.market_api.get_microstructure(focus_market)
        _merge_book_quotes(focus_market, book)
        prompt = _build_ai_prompt(focus_market, book)
        signal = await self.ai_engine.get_prediction(prompt)

        action = str(signal.get("action", "SKIP")).upper() if signal else "SKIP"
        confidence = safe_float(signal.get("confidence"), 0.0) if signal else 0.0
        reason = signal.get("reason", "AI 调用失败") if signal else "AI 调用失败"
        outcome_index = signal.get("outcome_index") if signal else None

        if not isinstance(outcome_index, int):
            outcome_index = None

        logger.info("💡 AI 决策: %s outcome=%s (%.0f%%) | %s", action, outcome_index, confidence * 100, reason)

        execution_summary = "未执行"
        chosen_outcome: Optional[Dict[str, Any]] = None
        min_confidence = Config.get_float("AI_MIN_CONFIDENCE", "0.6")

        if action == "BUY" and confidence >= min_confidence and outcome_index is not None:
            outcomes = focus_market.get("outcomes", [])
            if 0 <= outcome_index < len(outcomes):
                chosen_outcome = outcomes[outcome_index]
                entry_price = safe_float(chosen_outcome.get("best_ask"), chosen_outcome.get("price"))
                if entry_price and entry_price > 0:
                    quote = {
                        "token_id": chosen_outcome.get("token_id"),
                        "label": chosen_outcome.get("label"),
                        "outcome_index": chosen_outcome.get("index"),
                        "best_bid": chosen_outcome.get("best_bid"),
                        "best_ask": chosen_outcome.get("best_ask"),
                    }
                    execution_summary = await self.executor.open_position(
                        focus_market,
                        signal,
                        entry_price,
                        chosen_outcome.get("label", f"Outcome {outcome_index}"),
                        quote,
                    )
                else:
                    action = "SKIP"
                    reason = "目标 outcome 缺少有效价格"
                    execution_summary = reason
            else:
                action = "SKIP"
                reason = "AI 返回的 outcome_index 超出范围"
                execution_summary = reason
        elif action == "BUY":
            action = "SKIP"
            reason = "未达到最小信心阈值或缺少 outcome_index"
            execution_summary = reason
        else:
            execution_summary = "AI 选择观望"

        market_outcomes = []
        for outcome in focus_market.get("outcomes", []):
            market_outcomes.append({
                "index": outcome.get("index"),
                "label": outcome.get("label"),
                "price": outcome.get("price"),
                "best_bid": outcome.get("best_bid"),
                "best_ask": outcome.get("best_ask"),
            })

        selected_index = chosen_outcome.get("index") if action == "BUY" and chosen_outcome else None
        selected_label = chosen_outcome.get("label") if action == "BUY" and chosen_outcome else None

        StatusExporter.export({
            **base_status,
            "market_slug": focus_market.get("slug", ""),
            "market_question": focus_market.get("question", ""),
            "market_end_date": focus_market.get("end_date", ""),
            "market_outcomes": market_outcomes,
            "ai_prediction": action,
            "ai_action": action,
            "ai_confidence": confidence,
            "ai_outcome_index": selected_index,
            "ai_outcome_label": selected_label,
            "decision_reason": reason,
            "execution_summary": execution_summary,
        })

    async def start(self):
        logger.info("🤖 Polymarket 通用交易机器人启动")
        logger.info("📊 当前模式: %s", self.current_mode)

        while self.running:
            try:
                await self.run_cycle()
                interval = Config.get_int("PAPER_POLL_INTERVAL_SECONDS", "15")
                await asyncio.sleep(interval)
            except Exception as exc:
                logger.error("❌ 运行循环异常: %s", exc, exc_info=True)
                await asyncio.sleep(10)
