import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from ..core.config import (
    Config, PAPER_START_BALANCE, LIVE_BET_AMOUNT, 
    DRY_RUN, POLYMARKET_PRIVATE_KEY, POLYMARKET_WALLET_ADDRESS,
    POLYMARKET_API_KEY, POLYMARKET_API_SECRET, POLYMARKET_API_PASSPHRASE,
    POLYMARKET_FUNDER_ADDRESS, POLYMARKET_SIGNATURE_TYPE
)
from ..core.utils import safe_float, short_wallet
from .live_trader import LiveTrader

logger = logging.getLogger("trading_executor")

class BaseExecutor(ABC):
    """交易执行器基类"""
    def __init__(self, state_manager):
        self.state_manager = state_manager
        self.mode = "base"

    @abstractmethod
    async def open_position(self, snapshot: dict, signal: dict, entry_price: float, outcome: str, quote: dict) -> str:
        pass

    @abstractmethod
    async def close_position(self, position: dict, exit_price: float, exit_reason: str, signal: Optional[dict] = None) -> str:
        pass

    @abstractmethod
    def get_balances(self) -> Dict[str, float]:
        pass

class PaperExecutor(BaseExecutor):
    """模拟交易执行器: 纯本地状态维护"""
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.mode = "paper_live"

    def get_balances(self) -> Dict[str, float]:
        state = self.state_manager.get_state()
        reserved = sum(p.get("stake", 0.0) for p in state.get("positions", []))
        return {"cash": state.get("cash_balance", 0.0), "reserved": reserved}

    async def open_position(self, snapshot, signal, entry_price, outcome, quote) -> str:
        state = self.state_manager.get_state()
        stake = Config.get_float("PAPER_BET_AMOUNT", "5.0")
        
        # 资金检查
        if state["cash_balance"] < stake:
            return f"模拟资金不足: {state['cash_balance']:.2f} < {stake}"
        
        now_utc = datetime.now(timezone.utc)
        shares = round(stake / entry_price, 6)
        
        position = {
            "id": f"paper-{int(time.time())}",
            "market": snapshot.get("slug") or snapshot.get("question"),
            "market_slug": snapshot.get("slug"),
            "market_title": snapshot.get("question"),
            "end_date": snapshot.get("end_date"),
            "outcome": outcome,
            "outcome_name": outcome,
            "outcome_index": quote.get("outcome_index"),
            "token_id": quote.get("token_id"),
            "stake": stake,
            "size": shares,
            "shares": shares,
            "entry_price": entry_price,
            "current_bid": quote.get("best_bid"),
            "current_ask": quote.get("best_ask"),
            "created_at": now_utc.isoformat(),
            "opened_at": now_utc.isoformat(),
            "status": "OPEN"
        }

        trade = {
            "id": f"trade-{int(time.time())}",
            "decision_id": signal.get("decision_id") if signal else None,
            "created_at": now_utc.isoformat(),
            "side": "BUY",
            "outcome": outcome,
            "market": snapshot.get("question"),
            "market_slug": snapshot.get("slug"),
            "amount": stake,
            "size": shares,
            "price": entry_price,
            "status": "OPEN",
            "reason": signal.get("reason") if signal else "",
        }
        
        state["positions"].append(position)
        state.setdefault("trades", []).insert(0, trade)
        state["cash_balance"] = round(state["cash_balance"] - stake, 4)
        state["market"] = {
            "slug": snapshot.get("slug"),
            "question": snapshot.get("question"),
            "end_date": snapshot.get("end_date"),
        }
        self.state_manager.save()
        return f"模拟买入成功: {outcome} @ {entry_price}"

    async def close_position(self, position, exit_price, exit_reason, signal=None) -> str:
        state = self.state_manager.get_state()
        proceeds = round(position["shares"] * exit_price, 4)
        profit = round(proceeds - position["stake"], 4)
        
        state["cash_balance"] = round(state["cash_balance"] + proceeds, 4)
        state["positions"] = [p for p in state["positions"] if p["id"] != position["id"]]
        
        # 更新统计数据
        stats = state.setdefault("stats", {"total_trades": 0, "winning_trades": 0, "losing_trades": 0, "total_profit": 0.0})
        stats["total_trades"] += 1
        stats["total_profit"] = round(stats["total_profit"] + profit, 4)
        if profit >= 0:
            stats["winning_trades"] += 1
        else:
            stats["losing_trades"] += 1

        state.setdefault("trades", []).insert(0, {
            "id": f"trade-close-{int(time.time())}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "side": "SELL",
            "outcome": position.get("outcome"),
            "market": position.get("market_title") or position.get("market"),
            "market_slug": position.get("market_slug"),
            "amount": proceeds,
            "size": position.get("shares"),
            "price": exit_price,
            "status": exit_reason,
            "reason": exit_reason,
            "realized_profit": profit,
        })
        
        self.state_manager.save()
        return f"模拟平仓成功: {exit_reason}, 盈亏: {profit:+.2f}"

class LiveExecutor(BaseExecutor):
    """实盘交易执行器: 调用真官方 SDK"""
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.mode = "live"
        self._init_client()

    def _init_client(self):
        self.live_trader = LiveTrader(
            host="https://clob.polymarket.com",
            private_key=Config.get("POLYMARKET_PRIVATE_KEY"),
            funder_address=Config.get("POLYMARKET_FUNDER_ADDRESS"),
            signature_type=Config.get_int("POLYMARKET_SIGNATURE_TYPE", 1),
            api_creds={
                "key": Config.get("POLYMARKET_API_KEY"),
                "secret": Config.get("POLYMARKET_API_SECRET"),
                "passphrase": Config.get("POLYMARKET_API_PASSPHRASE")
            },
            dry_run=Config.get_bool("DRY_RUN", "true")
        )

    def get_balances(self) -> Dict[str, float]:
        try:
            res = self.live_trader.get_balances()
            return {"cash": res.get("USDC", 0.0), "reserved": 0.0}
        except:
            return {"cash": 0.0, "reserved": 0.0}

    async def open_position(self, snapshot, signal, entry_price, outcome, quote) -> str:
        token_id = quote.get("token_id")
        stake = Config.get_float("LIVE_BET_AMOUNT", "1.0")
        
        # 调用真正下单
        order_id = self.live_trader.buy(
            token_id=token_id,
            price=entry_price,
            size_usdc=stake,
            tick_size=snapshot.get("tick_size", "0.01"),
            neg_risk=snapshot.get("neg_risk", False),
        )
        if order_id:
            state = self.state_manager.get_state()
            state.setdefault("orders", []).insert(0, {
                "id": order_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "side": "BUY",
                "outcome": outcome,
                "outcome_index": quote.get("outcome_index"),
                "market": snapshot.get("question"),
                "market_slug": snapshot.get("slug"),
                "end_date": snapshot.get("end_date"),
                "price": entry_price,
                "amount": stake,
                "token_id": token_id,
                "status": "SUBMITTED",
                "reason": signal.get("reason") if signal else "",
            })
            self.state_manager.save()
            return f"实盘下单成功: {order_id}"
        return "实盘下单失败"

    async def close_position(self, position, exit_price, exit_reason, signal=None) -> str:
        # TODO: 实盘平仓逻辑
        return "实盘平仓执行"
