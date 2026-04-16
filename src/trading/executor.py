import logging
import math
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from py_clob_client.clob_types import TradeParams
from ..core.config import (
    Config, PAPER_START_BALANCE, LIVE_BET_AMOUNT, 
    DRY_RUN, POLYMARKET_PRIVATE_KEY, POLYMARKET_WALLET_ADDRESS,
    POLYMARKET_API_KEY, POLYMARKET_API_SECRET, POLYMARKET_API_PASSPHRASE,
    POLYMARKET_FUNDER_ADDRESS, POLYMARKET_SIGNATURE_TYPE
)
from ..core.utils import safe_float, short_wallet
from .live_trader import LiveTrader

logger = logging.getLogger("trading_executor")
ACTIVE_ORDER_STATUSES = {"SUBMITTED", "OPEN", "PENDING", "PENDING_FILL", "PARTIAL_FILL"}
EPSILON = 1e-6


def _estimate_limit_shares(price: float, size_usdc: float) -> float:
    if not price or price <= 0:
        return 0.0
    return math.ceil(size_usdc / price * 100) / 100


def _floor_shares(value: float, decimals: int = 2) -> float:
    factor = 10 ** decimals
    return math.floor(max(value, 0.0) * factor) / factor

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

    async def sync_state(self, markets_by_slug: Optional[Dict[str, Dict[str, Any]]] = None, now_utc: Optional[datetime] = None) -> List[str]:
        return []

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

    def _find_position(self, state: Dict[str, Any], *, position_id: Optional[str] = None, order: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        for position in state.get("positions", []):
            if position_id and position.get("id") == position_id:
                return position
            if order:
                if order.get("position_id") and position.get("id") == order.get("position_id"):
                    return position
                if order.get("entry_order_id") and position.get("entry_order_id") == order.get("entry_order_id"):
                    return position
                if order.get("token_id") and position.get("token_id") == order.get("token_id") and position.get("market_slug") == order.get("market_slug"):
                    return position
        return None

    def _aggregate_fills(self, tracked_ids: set[str], orders: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not tracked_ids:
            return {}

        oldest_created = None
        for order in orders:
            created_at = order.get("created_at")
            if not created_at:
                continue
            try:
                ts = int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
            except Exception:
                continue
            oldest_created = ts if oldest_created is None else min(oldest_created, ts)

        params = TradeParams(after=max(0, oldest_created - 300)) if oldest_created else TradeParams()
        trades = self.live_trader.get_trades(params)
        aggregated: Dict[str, Dict[str, Any]] = {}

        def _bucket(order_id: str) -> Dict[str, Any]:
            return aggregated.setdefault(order_id, {
                "filled_size": 0.0,
                "filled_value": 0.0,
                "last_fill_at": None,
                "fills": 0,
            })

        for trade in trades:
            match_ts = safe_float(trade.get("match_time"), safe_float(trade.get("last_update")))
            taker_order_id = trade.get("taker_order_id")
            if taker_order_id in tracked_ids:
                size = safe_float(trade.get("size"), 0.0) or 0.0
                price = safe_float(trade.get("price"), 0.0) or 0.0
                bucket = _bucket(taker_order_id)
                bucket["filled_size"] = round(bucket["filled_size"] + size, 8)
                bucket["filled_value"] = round(bucket["filled_value"] + size * price, 8)
                bucket["fills"] += 1
                bucket["last_fill_at"] = max(bucket["last_fill_at"] or 0, match_ts or 0)

            for maker_order in trade.get("maker_orders", []) or []:
                order_id = maker_order.get("order_id")
                if order_id not in tracked_ids:
                    continue
                size = safe_float(maker_order.get("matched_amount"), safe_float(trade.get("size"), 0.0)) or 0.0
                price = safe_float(maker_order.get("price"), safe_float(trade.get("price"), 0.0)) or 0.0
                bucket = _bucket(order_id)
                bucket["filled_size"] = round(bucket["filled_size"] + size, 8)
                bucket["filled_value"] = round(bucket["filled_value"] + size * price, 8)
                bucket["fills"] += 1
                bucket["last_fill_at"] = max(bucket["last_fill_at"] or 0, match_ts or 0)

        return aggregated

    def _record_live_trade(
        self,
        state: Dict[str, Any],
        *,
        order: Dict[str, Any],
        created_at: str,
        side: str,
        size: float,
        price: float,
        amount: float,
        status: str,
        reason: str,
        realized_profit: Optional[float] = None,
    ):
        trade = {
            "id": f"live-trade-{order.get('id')}-{int(time.time() * 1000)}",
            "order_id": order.get("id"),
            "created_at": created_at,
            "side": side,
            "outcome": order.get("outcome"),
            "market": order.get("market"),
            "market_slug": order.get("market_slug"),
            "amount": round(amount, 4),
            "size": round(size, 6),
            "price": round(price, 6),
            "status": status,
            "reason": reason,
        }
        if realized_profit is not None:
            trade["realized_profit"] = round(realized_profit, 4)
        state.setdefault("trades", []).insert(0, trade)

    def _reconcile_position_balance(self, position: Dict[str, Any]) -> float:
        token_id = position.get("token_id")
        if not token_id:
            return safe_float(position.get("shares"), safe_float(position.get("size"), 0.0)) or 0.0

        available = self.live_trader.get_token_balance(token_id)
        local_shares = safe_float(position.get("shares"), safe_float(position.get("size"), 0.0)) or 0.0
        if available > EPSILON and local_shares > EPSILON and available + EPSILON < local_shares:
            position["shares"] = round(available, 8)
            position["size"] = position["shares"]
            stake = safe_float(position.get("stake"), 0.0) or 0.0
            if position["shares"] > EPSILON and stake > 0:
                position["entry_price"] = round(stake / position["shares"], 8)
        return available

    def _apply_buy_fill(self, state: Dict[str, Any], order: Dict[str, Any], delta_size: float, delta_value: float, fill_at: Optional[float]) -> Optional[str]:
        if delta_size <= EPSILON or delta_value <= 0:
            return None

        avg_price = delta_value / delta_size
        created_at = datetime.fromtimestamp(fill_at, tz=timezone.utc).isoformat() if fill_at else datetime.now(timezone.utc).isoformat()
        position = self._find_position(state, order=order)
        if position:
            position["shares"] = round((safe_float(position.get("shares"), 0.0) or 0.0) + delta_size, 8)
            position["size"] = position["shares"]
            position["stake"] = round((safe_float(position.get("stake"), 0.0) or 0.0) + delta_value, 8)
            position["entry_price"] = round(position["stake"] / position["shares"], 8) if position["shares"] > EPSILON else avg_price
            position["status"] = "OPEN"
            position.setdefault("opened_at", created_at)
        else:
            position_id = order.get("position_id") or f"live-pos-{order.get('id')}"
            position = {
                "id": position_id,
                "entry_order_id": order.get("id"),
                "market": order.get("market_slug") or order.get("market"),
                "market_slug": order.get("market_slug"),
                "market_title": order.get("market"),
                "end_date": order.get("end_date"),
                "outcome": order.get("outcome"),
                "outcome_name": order.get("outcome"),
                "outcome_index": order.get("outcome_index"),
                "token_id": order.get("token_id"),
                "stake": round(delta_value, 8),
                "size": round(delta_size, 8),
                "shares": round(delta_size, 8),
                "entry_price": round(avg_price, 8),
                "current_bid": order.get("price"),
                "current_ask": order.get("price"),
                "created_at": order.get("created_at") or created_at,
                "opened_at": created_at,
                "status": "OPEN",
            }
            state.setdefault("positions", []).append(position)
            order["position_id"] = position_id

        actual_shares = self._reconcile_position_balance(position)
        if actual_shares > EPSILON:
            position["current_bid"] = order.get("price")
            position["current_ask"] = order.get("price")

        self._record_live_trade(
            state,
            order=order,
            created_at=created_at,
            side="BUY",
            size=delta_size,
            price=avg_price,
            amount=delta_value,
            status="FILLED",
            reason=order.get("reason", ""),
        )
        return f"实盘买单成交: {order.get('outcome')} {delta_size:.4f} 股 @ {avg_price:.3f}"

    def _apply_sell_fill(self, state: Dict[str, Any], order: Dict[str, Any], delta_size: float, delta_value: float, fill_at: Optional[float]) -> Optional[str]:
        if delta_size <= EPSILON or delta_value < 0:
            return None

        position = self._find_position(state, position_id=order.get("position_id"), order=order)
        if not position:
            logger.warning("未找到待平仓持仓，跳过 SELL fill 回补: %s", order.get("id"))
            return None

        old_shares = safe_float(position.get("shares"), 0.0) or 0.0
        old_stake = safe_float(position.get("stake"), 0.0) or 0.0
        if old_shares <= EPSILON:
            return None

        close_shares = min(delta_size, old_shares)
        avg_entry = old_stake / old_shares if old_shares > EPSILON else 0.0
        cost_basis = avg_entry * close_shares
        profit = delta_value - cost_basis
        remaining_shares = max(0.0, old_shares - close_shares)
        remaining_stake = max(0.0, old_stake - cost_basis)

        position["shares"] = round(remaining_shares, 8)
        position["size"] = position["shares"]
        position["stake"] = round(remaining_stake, 8)
        position["entry_price"] = round(remaining_stake / remaining_shares, 8) if remaining_shares > EPSILON else safe_float(position.get("entry_price"), 0.0)
        if remaining_shares <= EPSILON:
            state["positions"] = [item for item in state.get("positions", []) if item.get("id") != position.get("id")]
        else:
            position["status"] = "OPEN"

        stats = state.setdefault("stats", {"total_trades": 0, "winning_trades": 0, "losing_trades": 0, "total_profit": 0.0})
        stats["total_trades"] += 1
        stats["total_profit"] = round((safe_float(stats.get("total_profit"), 0.0) or 0.0) + profit, 4)
        if profit >= 0:
            stats["winning_trades"] += 1
        else:
            stats["losing_trades"] += 1

        avg_exit = delta_value / close_shares if close_shares > EPSILON else safe_float(order.get("price"), 0.0)
        created_at = datetime.fromtimestamp(fill_at, tz=timezone.utc).isoformat() if fill_at else datetime.now(timezone.utc).isoformat()
        self._record_live_trade(
            state,
            order=order,
            created_at=created_at,
            side="SELL",
            size=close_shares,
            price=avg_exit,
            amount=delta_value,
            status=order.get("close_reason") or "FILLED",
            reason=order.get("close_reason") or order.get("reason", ""),
            realized_profit=profit,
        )
        return f"实盘卖单成交: {order.get('outcome')} {close_shares:.4f} 股, 盈亏 {profit:+.2f}"

    async def sync_state(self, markets_by_slug: Optional[Dict[str, Dict[str, Any]]] = None, now_utc: Optional[datetime] = None) -> List[str]:
        state = self.state_manager.get_state()
        orders = state.get("orders", [])
        tracked_orders = [order for order in orders if order.get("status") not in {"FILLED", "CANCELLED", "EXPIRED", "REJECTED"}]
        if not tracked_orders:
            return []

        live_open_orders = self.live_trader.get_open_orders()
        open_order_ids = {
            item.get("id") or item.get("orderID") or item.get("order_id")
            for item in live_open_orders
            if item.get("id") or item.get("orderID") or item.get("order_id")
        }
        tracked_ids = {order.get("id") for order in tracked_orders if order.get("id")}
        fills_by_order = self._aggregate_fills(tracked_ids, tracked_orders)

        messages: List[str] = []
        changed = False
        now_utc = now_utc or datetime.now(timezone.utc)

        for order in tracked_orders:
            order_id = order.get("id")
            fills = fills_by_order.get(order_id, {})
            filled_size = safe_float(fills.get("filled_size"), 0.0) or 0.0
            filled_value = safe_float(fills.get("filled_value"), 0.0) or 0.0
            prev_size = safe_float(order.get("synced_filled_size"), 0.0) or 0.0
            prev_value = safe_float(order.get("synced_filled_value"), 0.0) or 0.0
            delta_size = round(filled_size - prev_size, 8)
            delta_value = round(filled_value - prev_value, 8)

            if delta_size > EPSILON:
                if order.get("side") == "BUY":
                    message = self._apply_buy_fill(state, order, delta_size, delta_value, fills.get("last_fill_at"))
                else:
                    message = self._apply_sell_fill(state, order, delta_size, delta_value, fills.get("last_fill_at"))
                if message:
                    messages.append(message)
                order["synced_filled_size"] = round(filled_size, 8)
                order["synced_filled_value"] = round(filled_value, 8)
                if fills.get("last_fill_at"):
                    order["last_fill_at"] = datetime.fromtimestamp(fills["last_fill_at"], tz=timezone.utc).isoformat()
                changed = True

            target_size = safe_float(order.get("size"), safe_float(order.get("shares_target"), 0.0)) or 0.0
            market_slug = order.get("market_slug")
            market = (markets_by_slug or {}).get(market_slug or "")
            market_closed = bool(market.get("closed")) if market else False
            end_date = order.get("end_date")
            if end_date:
                try:
                    market_closed = market_closed or datetime.fromisoformat(end_date.replace("Z", "+00:00")) <= now_utc
                except Exception:
                    pass

            new_status = order.get("status", "SUBMITTED")
            if order_id in open_order_ids:
                new_status = "PENDING_FILL" if filled_size > EPSILON else "SUBMITTED"
                if market_closed:
                    cancel_resp = self.live_trader.cancel_order(order_id)
                    if cancel_resp is not None:
                        new_status = "EXPIRED"
                        messages.append(f"已撤销临近/到期挂单: {order.get('outcome')} {order_id}")
            else:
                if filled_size > EPSILON and target_size > EPSILON and filled_size + EPSILON < target_size:
                    new_status = "PARTIAL_FILL"
                elif filled_size > EPSILON:
                    new_status = "FILLED"
                elif market_closed:
                    new_status = "EXPIRED"
                else:
                    new_status = "CANCELLED"

            if new_status != order.get("status"):
                order["status"] = new_status
                changed = True

        if changed:
            self.state_manager.save()
        return messages

    async def open_position(self, snapshot, signal, entry_price, outcome, quote) -> str:
        token_id = quote.get("token_id")
        stake = Config.get_float("LIVE_BET_AMOUNT", "1.0")
        estimated_shares = _estimate_limit_shares(entry_price, stake)
        
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
                "size": estimated_shares,
                "shares_target": estimated_shares,
                "synced_filled_size": 0.0,
                "synced_filled_value": 0.0,
                "token_id": token_id,
                "status": "SUBMITTED",
                "reason": signal.get("reason") if signal else "",
            })
            self.state_manager.save()
            return f"实盘下单成功: {order_id}"
        return "实盘下单失败"

    async def close_position(self, position, exit_price, exit_reason, signal=None) -> str:
        state = self.state_manager.get_state()
        if any(
            order.get("status") in ACTIVE_ORDER_STATUSES
            and order.get("side") == "SELL"
            and order.get("position_id") == position.get("id")
            for order in state.get("orders", [])
        ):
            return f"已有实盘平仓单在途: {position.get('outcome_name') or position.get('outcome')}"

        local_shares = safe_float(position.get("shares"), safe_float(position.get("size"), 0.0)) or 0.0
        if local_shares <= EPSILON:
            return "持仓数量为 0，跳过实盘平仓"

        available_shares = self._reconcile_position_balance(position)
        if available_shares > EPSILON:
            shares = min(local_shares, available_shares)
        else:
            shares = local_shares
        shares = _floor_shares(shares, 2)
        if shares <= EPSILON:
            return "可卖份额不足，跳过实盘平仓"

        order_id = self.live_trader.sell(
            token_id=position.get("token_id"),
            price=exit_price,
            size_shares=shares,
            tick_size=position.get("tick_size", "0.01"),
            neg_risk=bool(position.get("neg_risk", False)),
        )
        if not order_id:
            return "实盘平仓下单失败"

        order = {
            "id": order_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "side": "SELL",
            "position_id": position.get("id"),
            "entry_order_id": position.get("entry_order_id"),
            "outcome": position.get("outcome_name") or position.get("outcome"),
            "outcome_index": position.get("outcome_index"),
            "market": position.get("market_title") or position.get("market"),
            "market_slug": position.get("market_slug"),
            "end_date": position.get("end_date"),
            "price": exit_price,
            "amount": round(shares * exit_price, 8),
            "size": round(shares, 8),
            "shares_target": round(shares, 8),
            "synced_filled_size": 0.0,
            "synced_filled_value": 0.0,
            "token_id": position.get("token_id"),
            "status": "SUBMITTED",
            "reason": signal.get("reason") if signal else exit_reason,
            "close_reason": exit_reason,
        }
        state.setdefault("orders", []).insert(0, order)
        position["status"] = "CLOSING"
        self.state_manager.save()
        return f"实盘平仓单已提交: {exit_reason} @ {exit_price}"
