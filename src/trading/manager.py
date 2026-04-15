import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..ai.decision import AIDecisionEngine
from ..api.market import PolymarketClient
from ..core.config import Config, CONTROL_FILE, PAPER_STATE_FILE
from ..core.state import StateManager, StatusExporter
from ..core.utils import iso_to_utc_dt, load_trading_control, safe_float
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

    def _find_outcome(self, market: Dict[str, Any], position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for outcome in market.get("outcomes", []):
            if position.get("token_id") and position.get("token_id") == outcome.get("token_id"):
                return outcome
            if position.get("outcome_index") is not None and position.get("outcome_index") == outcome.get("index"):
                return outcome
        return None

    def _build_market_outcomes(self, market: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "index": outcome.get("index"),
                "label": outcome.get("label"),
                "price": outcome.get("price"),
                "best_bid": outcome.get("best_bid"),
                "best_ask": outcome.get("best_ask"),
            }
            for outcome in market.get("outcomes", [])
        ]

    def _refresh_summary(self):
        state = self.state_manager.get_state()
        positions = state.get("positions", [])
        stats = state.get("stats", {})
        reserved_balance = round(sum(safe_float(pos.get("stake"), 0.0) or 0.0 for pos in positions), 4)
        unrealized_pnl = 0.0
        for position in positions:
            shares = safe_float(position.get("shares"), safe_float(position.get("size"), 0.0)) or 0.0
            current_bid = safe_float(position.get("current_bid"), safe_float(position.get("entry_price"), 0.0)) or 0.0
            stake = safe_float(position.get("stake"), 0.0) or 0.0
            unrealized_pnl += round(shares * current_bid - stake, 4)

        cash_balance = round(safe_float(state.get("cash_balance"), 0.0) or 0.0, 4)
        realized_pnl = round(safe_float(stats.get("total_profit"), 0.0) or 0.0, 4)
        ending_balance = round(cash_balance + reserved_balance + unrealized_pnl, 4)
        total_trades = int(stats.get("total_trades", 0) or 0)
        winning_trades = int(stats.get("winning_trades", 0) or 0)
        win_rate = round((winning_trades / total_trades) * 100, 2) if total_trades else 0.0
        paper_start = Config.get_float("PAPER_START_BALANCE", "100")
        roi_percent = round(((ending_balance - paper_start) / paper_start) * 100, 2) if paper_start else 0.0

        state["summary"] = {
            "cash_balance": cash_balance,
            "reserved_balance": reserved_balance,
            "ending_balance": ending_balance,
            "open_positions": len(positions),
            "realized_pnl": realized_pnl,
            "unrealized_pnl": round(unrealized_pnl, 4),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": win_rate,
            "session_started_at": state.get("session_started_at"),
        }
        state["report"] = {
            "strategy": "Generic Binary V1.1",
            "profit": round(realized_pnl + unrealized_pnl, 4),
            "roi_percent": roi_percent,
            "result": "running",
            "session_started_at": state.get("session_started_at"),
        }
        self.state_manager.save()

    async def _load_markets_for_positions(self, current_market: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        state = self.state_manager.get_state()
        slugs = {
            pos.get("market_slug")
            for pos in state.get("positions", [])
            if pos.get("status", "OPEN") == "OPEN" and pos.get("market_slug")
        }
        if current_market and current_market.get("slug"):
            slugs.add(current_market["slug"])

        async def _load(slug: str) -> Tuple[str, Optional[Dict[str, Any]]]:
            market = current_market if current_market and current_market.get("slug") == slug else await self.market_api.get_market(slug)
            if market:
                book = await self.market_api.get_microstructure(market)
                _merge_book_quotes(market, book)
            return slug, market

        markets: Dict[str, Dict[str, Any]] = {}
        if not slugs:
            return markets
        results = await asyncio.gather(*[_load(slug) for slug in slugs])
        for slug, market in results:
            if market:
                markets[slug] = market
        return markets

    def _should_close_position(
        self,
        now_utc: datetime,
        market: Dict[str, Any],
        position: Dict[str, Any],
        outcome: Dict[str, Any],
    ) -> Tuple[Optional[float], Optional[str]]:
        exit_price = safe_float(outcome.get("best_bid"), safe_float(outcome.get("price"), position.get("current_bid")))
        if exit_price is None or exit_price <= 0:
            return None, None

        end_date = market.get("end_date") or position.get("end_date")
        is_closed = bool(market.get("closed"))
        if end_date:
            try:
                is_closed = is_closed or iso_to_utc_dt(end_date) <= now_utc
            except Exception:
                pass
        if is_closed:
            return exit_price, "EXPIRY_EXIT"

        stake = safe_float(position.get("stake"), 0.0) or 0.0
        shares = safe_float(position.get("shares"), safe_float(position.get("size"), 0.0)) or 0.0
        pnl = shares * exit_price - stake

        take_profit_usd = Config.get_float("PAPER_TAKE_PROFIT_USD", "0.12")
        if pnl >= take_profit_usd:
            return exit_price, "TAKE_PROFIT"

        if Config.get_bool("STOP_LOSS_ENABLED", "true") and stake > 0:
            stop_loss_usd = stake * Config.get_float("STOP_LOSS_PERCENT", "0.10")
            if pnl <= -stop_loss_usd:
                return exit_price, "STOP_LOSS"

        return None, None

    async def _manage_open_positions(self, now_utc: datetime, current_market: Optional[Dict[str, Any]]) -> List[str]:
        if not self.current_mode.startswith("paper"):
            return []

        markets = await self._load_markets_for_positions(current_market)
        state = self.state_manager.get_state()
        close_messages: List[str] = []
        updated = False

        for position in list(state.get("positions", [])):
            if position.get("status", "OPEN") != "OPEN":
                continue
            market_slug = position.get("market_slug")
            market = markets.get(market_slug or "")
            if not market:
                continue
            outcome = self._find_outcome(market, position)
            if not outcome:
                continue

            position["current_bid"] = safe_float(outcome.get("best_bid"), position.get("current_bid"))
            position["current_ask"] = safe_float(outcome.get("best_ask"), position.get("current_ask"))
            updated = True

            exit_price, exit_reason = self._should_close_position(now_utc, market, position, outcome)
            if exit_price is None or not exit_reason:
                continue

            message = await self.executor.close_position(position, exit_price, exit_reason)
            close_messages.append(message)

        if updated and not close_messages:
            self.state_manager.save()
        self._refresh_summary()
        return close_messages

    def _find_duplicate_exposure(self, market: Dict[str, Any]) -> Optional[str]:
        state = self.state_manager.get_state()
        market_slug = market.get("slug")
        for position in state.get("positions", []):
            if position.get("status", "OPEN") == "OPEN" and position.get("market_slug") == market_slug:
                return f"已有持仓 {position.get('outcome_name') or position.get('outcome')}"

        active_statuses = {"SUBMITTED", "OPEN", "PENDING", "PENDING_FILL"}
        for order in state.get("orders", []):
            if order.get("status") in active_statuses and order.get("market_slug") == market_slug:
                end_date = order.get("end_date")
                if end_date:
                    try:
                        if iso_to_utc_dt(end_date) <= datetime.now(timezone.utc):
                            continue
                    except Exception:
                        pass
                return f"已有挂单 {order.get('outcome') or order.get('outcome_name')}"
        return None

    def _max_open_exposure(self) -> int:
        if self.current_mode == "live":
            return Config.get_int("LIVE_MAX_OPEN_POSITIONS", "1")
        return Config.get_int("PAPER_MAX_OPEN_POSITIONS", "1")

    def _open_exposure_count(self) -> int:
        state = self.state_manager.get_state()
        open_positions = sum(1 for pos in state.get("positions", []) if pos.get("status", "OPEN") == "OPEN")
        active_orders = sum(
            1 for order in state.get("orders", [])
            if order.get("status") in {"SUBMITTED", "OPEN", "PENDING", "PENDING_FILL"}
        )
        return open_positions + active_orders

    def _record_ai_history(
        self,
        now_utc: datetime,
        market: Optional[Dict[str, Any]],
        action: str,
        confidence: float,
        reason: str,
        execution_summary: str,
        selected_label: Optional[str],
    ):
        state = self.state_manager.get_state()
        market_outcomes = self._build_market_outcomes(market) if market else []
        history = state.setdefault("ai_history", [])
        history.insert(0, {
            "decision_id": f"LOCAL-{now_utc.strftime('%Y%m%d-%H%M%S')}",
            "generated_at": now_utc.isoformat(),
            "action": action,
            "decision": action,
            "prediction": action,
            "confidence": confidence,
            "model": Config.get("AI_MODEL", "gpt-4o-mini"),
            "reasoning": reason,
            "thought_markdown": reason,
            "key_factors": [
                f"市场: {market.get('question', '--') if market else '--'}",
                f"选择结果: {selected_label or '--'}",
                "盘口: " + (" | ".join(
                    f"[{item.get('index')}] {item.get('label')} @ {item.get('price', '--')}" for item in market_outcomes
                ) if market_outcomes else "--"),
            ],
            "risk_flags": [],
            "execution_summary": execution_summary,
            "focus_market": market.get("question", "") if market else "",
        })
        state["ai_history"] = history[:20]
        self.state_manager.save()

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

        focus_market = await self.market_api.get_focus_market(now_utc)
        if focus_market and (not focus_market.get("binary") and not Config.get_bool("ALLOW_MULTI_OUTCOME", "false")):
            logger.warning("⚠️ 当前版本仅支持二元盘口: %s", focus_market.get("slug"))
            StatusExporter.export({
                **base_status,
                "market_slug": focus_market.get("slug", ""),
                "market_question": focus_market.get("question", ""),
                "market_end_date": focus_market.get("end_date", ""),
                "market_error": "当前版本仅支持二元盘口",
            })
            return

        close_messages = await self._manage_open_positions(now_utc, focus_market)

        if not is_enabled:
            logger.info("⏸ 交易已在控制台关闭，本轮跳过执行")
            execution_summary = "交易关闭" + (f"；{len(close_messages)} 笔持仓已处理" if close_messages else "")
            StatusExporter.export({**base_status, "execution_summary": execution_summary})
            return

        if not focus_market:
            logger.warning("⚠️ 未找到目标盘口，请先配置 TARGET_MARKET_SLUG / TARGET_MARKET_URL")
            StatusExporter.export({
                **base_status,
                "market_error": "未配置或无法解析目标市场",
                "execution_summary": "未执行",
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

        duplicate_reason = self._find_duplicate_exposure(focus_market)
        if duplicate_reason:
            action = "SKIP"
            reason = f"阻止重复开仓：{duplicate_reason}"
            execution_summary = reason
        elif self._open_exposure_count() >= self._max_open_exposure():
            action = "SKIP"
            reason = "已达到最大开仓数量限制"
            execution_summary = reason
        elif action == "BUY" and confidence >= min_confidence and outcome_index is not None:
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
                    if "成功" not in execution_summary:
                        action = "SKIP"
                        reason = execution_summary
                        chosen_outcome = None
                    self._refresh_summary()
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

        market_outcomes = self._build_market_outcomes(focus_market)
        selected_index = chosen_outcome.get("index") if action == "BUY" and chosen_outcome else None
        selected_label = chosen_outcome.get("label") if action == "BUY" and chosen_outcome else None
        if close_messages:
            execution_summary = "；".join(close_messages + ([execution_summary] if execution_summary else []))

        self._record_ai_history(
            now_utc=now_utc,
            market=focus_market,
            action=action,
            confidence=confidence,
            reason=reason,
            execution_summary=execution_summary,
            selected_label=selected_label,
        )

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
