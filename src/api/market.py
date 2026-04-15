import aiohttp
import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.config import Config
from ..core.utils import extract_market_slug, parse_json_list, safe_float

logger = logging.getLogger("market_api")

# Legacy BTC 15m scanner support
BTC_15M_SLUG_PREFIX = "btc-updown-15m-"
WINDOW_SECONDS = 900  # 15 minutes


def _complement_price(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(max(0.0, min(1.0, 1 - float(value))), 4)


class PolymarketClient:
    """Polymarket public market data wrapper."""

    def __init__(self):
        self.BASE_URL = "https://gamma-api.polymarket.com"
        self.headers = {"Accept": "application/json"}

    def _current_window_slugs(self, now_utc: datetime, lookahead: int = 3) -> List[str]:
        """Generate current and near-future BTC 15m slugs for legacy auto-discovery."""
        ts = int(now_utc.timestamp())
        base = math.ceil(ts / WINDOW_SECONDS) * WINDOW_SECONDS
        return [f"{BTC_15M_SLUG_PREFIX}{base + i * WINDOW_SECONDS}" for i in range(lookahead)]

    def _build_outcomes(self, raw_market: Dict[str, Any]) -> List[Dict[str, Any]]:
        token_ids = parse_json_list(raw_market.get("clobTokenIds"))
        labels = parse_json_list(raw_market.get("outcomes"))
        prices_raw = parse_json_list(raw_market.get("outcomePrices"))

        outcomes: List[Dict[str, Any]] = []
        for index, token_id in enumerate(token_ids):
            label = str(labels[index]) if index < len(labels) else f"Outcome {index + 1}"
            price = safe_float(prices_raw[index] if index < len(prices_raw) else None)
            outcomes.append({
                "index": index,
                "label": label,
                "token_id": token_id,
                "price": price,
                "best_bid": None,
                "best_ask": None,
            })

        market_best_bid = safe_float(raw_market.get("bestBid"))
        market_best_ask = safe_float(raw_market.get("bestAsk"))
        if outcomes:
            outcomes[0]["best_bid"] = market_best_bid
            outcomes[0]["best_ask"] = market_best_ask
        if len(outcomes) == 2:
            outcomes[1]["best_bid"] = _complement_price(market_best_ask)
            outcomes[1]["best_ask"] = _complement_price(market_best_bid)

        return outcomes

    def _normalize_market(
        self,
        raw_market: Dict[str, Any],
        *,
        slug_hint: str = "",
        question: Optional[str] = None,
        end_date: Optional[str] = None,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
        liquidity: Optional[float] = None,
        neg_risk: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        outcomes = self._build_outcomes(raw_market)
        if not outcomes:
            return None

        token_ids = [item["token_id"] for item in outcomes]
        prices = [item["price"] for item in outcomes]
        slug = str(raw_market.get("slug") or slug_hint or "").strip()
        is_binary = len(outcomes) == 2

        return {
            "slug": slug,
            "question": question or raw_market.get("question") or raw_market.get("title") or raw_market.get("name") or "",
            "end_date": end_date or raw_market.get("endDate"),
            "active": bool(raw_market.get("active", active if active is not None else True)),
            "closed": bool(raw_market.get("closed", closed if closed is not None else False)),
            "liquidity": safe_float(raw_market.get("liquidity"), liquidity if liquidity is not None else 0.0) or 0.0,
            "outcomes": outcomes,
            "outcome_count": len(outcomes),
            "binary": is_binary,
            "prices": prices,
            "token_ids": token_ids,
            "up_token_id": token_ids[0] if len(token_ids) > 0 else None,
            "down_token_id": token_ids[1] if len(token_ids) > 1 else None,
            "best_bid": outcomes[0]["best_bid"] if outcomes else None,
            "best_ask": outcomes[0]["best_ask"] if outcomes else None,
            "neg_risk": bool(raw_market.get("negRisk", neg_risk if neg_risk is not None else False)),
            "tick_size": str(raw_market.get("orderPriceMinTickSize", "0.01")),
            "accepting_orders": raw_market.get("acceptingOrders", True),
        }

    def _pick_market_from_event(self, event: Dict[str, Any], slug_hint: str) -> Optional[Dict[str, Any]]:
        markets = [market for market in (event.get("markets") or []) if parse_json_list(market.get("clobTokenIds"))]
        if not markets:
            return None

        for market in markets:
            if str(market.get("slug") or "").strip() == slug_hint:
                return market

        if len(markets) == 1:
            return markets[0]

        binary_markets = [market for market in markets if len(parse_json_list(market.get("clobTokenIds"))) == 2]
        if len(binary_markets) == 1:
            return binary_markets[0]

        logger.warning("事件 %s 包含多个可交易市场，请直接使用具体 market slug", slug_hint)
        return None

    async def _fetch_market_by_market_slug(
        self,
        session: aiohttp.ClientSession,
        slug: str,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.BASE_URL}/markets/slug/{slug}"
        try:
            async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                raw_market = await resp.json()
                if not raw_market or raw_market.get("error"):
                    return None
                return self._normalize_market(raw_market, slug_hint=slug)
        except Exception as exc:
            logger.debug("fetch_market_by_slug %s: %s", slug, exc)
            return None

    async def _fetch_event_by_slug(
        self,
        session: aiohttp.ClientSession,
        slug: str,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.BASE_URL}/events?slug={slug}"
        try:
            async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data:
                    return None
                event = data[0]
                if event.get("closed") or not event.get("active"):
                    return None
                market = self._pick_market_from_event(event, slug)
                if not market:
                    return None
                return self._normalize_market(
                    market,
                    slug_hint=str(market.get("slug") or slug),
                    question=event.get("title"),
                    end_date=event.get("endDate"),
                    active=event.get("active"),
                    closed=event.get("closed"),
                    liquidity=safe_float(event.get("liquidity"), 0.0),
                    neg_risk=event.get("negRisk", False),
                )
        except Exception as exc:
            logger.debug("fetch_event_by_slug %s: %s", slug, exc)
            return None

    async def get_market(self, market_input: str) -> Optional[Dict[str, Any]]:
        """Resolve a target market from a slug or Polymarket URL."""
        slug = extract_market_slug(market_input)
        if not slug:
            return None

        async with aiohttp.ClientSession() as session:
            market = await self._fetch_market_by_market_slug(session, slug)
            if market:
                return market
            return await self._fetch_event_by_slug(session, slug)

    async def get_focus_market(self, now_utc: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Return the configured target market, or legacy BTC 15m discovery if requested."""
        target_input = (
            Config.get("TARGET_MARKET_URL", "")
            or Config.get("TARGET_MARKET_SLUG", "")
            or Config.get("BTC_UPDOWN_MARKET_ID", "")
        )
        if target_input:
            market = await self.get_market(target_input)
            if market:
                return market
            logger.warning("未能解析目标市场: %s", target_input)

        if Config.get("MARKET_SELECTION_MODE", "manual").strip().lower() == "auto_btc_15m":
            snapshots = await self.get_market_snapshots(now_utc or datetime.now(timezone.utc))
            return snapshots[0] if snapshots else None
        return None

    async def get_market_snapshots(self, now_utc: datetime) -> List[Dict[str, Any]]:
        """Legacy BTC 15m active market discovery."""
        slugs = self._current_window_slugs(now_utc, lookahead=4)
        results = []
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_event_by_slug(session, slug) for slug in slugs]
            for snapshot in await asyncio.gather(*tasks):
                if snapshot:
                    results.append(snapshot)
        if results:
            logger.info("找到 %s 个活跃 BTC 15m 盘口: %s", len(results), [item["slug"] for item in results])
        else:
            logger.warning("未找到活跃的 BTC 15m 盘口（市场可能尚未开放或已全部关闭）")
        return results

    async def get_order_book(
        self,
        token_id: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch CLOB order book for a token."""
        if not token_id:
            return None

        url = f"https://clob.polymarket.com/book?token_id={token_id}"

        async def _request(client: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
            try:
                async with client.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception as exc:
                logger.debug("order_book %s: %s", token_id, exc)
            return None

        if session is not None:
            return await _request(session)

        async with aiohttp.ClientSession() as client:
            return await _request(client)

    async def get_microstructure(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch top-of-book data for each outcome in the target market."""
        outcomes = market.get("outcomes") or []
        if not outcomes:
            return {"outcomes": [], "source": "none"}

        async with aiohttp.ClientSession() as session:
            tasks = [self.get_order_book(outcome.get("token_id"), session=session) for outcome in outcomes]
            books = await asyncio.gather(*tasks)

        result = []
        for outcome, book in zip(outcomes, books):
            if not book:
                continue
            result.append({
                "index": outcome.get("index"),
                "label": outcome.get("label"),
                "token_id": outcome.get("token_id"),
                "bids": (book.get("bids") or [])[:5],
                "asks": (book.get("asks") or [])[:5],
            })
        return {"outcomes": result, "source": "clob" if result else "none"}


class BTCDataprovider:
    """Optional BTC price feed kept for dashboard/reference use."""

    async def get_price(self) -> Optional[Dict[str, Any]]:
        source = Config.get("BTC_PRICE_SOURCE", "binance")
        if source == "binance":
            return await self._get_binance_price()
        return await self._get_coingecko_price()

    async def _get_binance_price(self) -> Optional[Dict[str, Any]]:
        url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "price": float(data["lastPrice"]),
                            "change_24h": float(data["priceChangePercent"]),
                            "source": "binance",
                        }
            except Exception as exc:
                logger.error("Binance API error: %s", exc)
        return None

    async def _get_coingecko_price(self) -> Optional[Dict[str, Any]]:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        btc = data.get("bitcoin", {})
                        return {
                            "price": float(btc.get("usd", 0)),
                            "change_24h": float(btc.get("usd_24h_change", 0)),
                            "source": "coingecko",
                        }
            except Exception as exc:
                logger.error("CoinGecko API error: %s", exc)
        return None
