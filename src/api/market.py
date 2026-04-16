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
DEFAULT_REASONABLE_SPREAD = 0.25


def _complement_price(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(max(0.0, min(1.0, 1 - float(value))), 4)


def _quote_is_reasonable(
    bid: Optional[float],
    ask: Optional[float],
    reference_price: Optional[float] = None,
) -> bool:
    bid = safe_float(bid)
    ask = safe_float(ask)
    reference_price = safe_float(reference_price)
    if bid is None or ask is None:
        return False
    if bid <= 0 or ask <= 0 or bid >= ask or ask >= 1:
        return False
    spread = ask - bid
    if spread > DEFAULT_REASONABLE_SPREAD:
        return False
    if reference_price is not None:
        midpoint = (bid + ask) / 2
        if abs(midpoint - reference_price) > 0.2 and spread > 0.12:
            return False
    return True


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

    def _score_btc_snapshot(self, market: Dict[str, Any], now_utc: datetime) -> float:
        score = 0.0
        outcomes = market.get("outcomes") or []
        primary = outcomes[0] if outcomes else {}
        if _quote_is_reasonable(primary.get("best_bid"), primary.get("best_ask"), primary.get("price")):
            score += 10.0
        else:
            score -= 10.0

        end_date = market.get("end_date")
        if end_date:
            try:
                minutes_to_expiry = (datetime.fromisoformat(end_date.replace("Z", "+00:00")) - now_utc).total_seconds() / 60
                min_minutes = Config.get_int("PAPER_MIN_MINUTES_TO_EXPIRY", "3")
                if minutes_to_expiry >= min_minutes:
                    score += min(minutes_to_expiry, 30) / 5
                else:
                    score -= 20.0
            except Exception:
                pass

        liquidity = safe_float(market.get("liquidity"), 0.0) or 0.0
        score += min(liquidity, 5000.0) / 1000.0
        return score

    def _select_btc_snapshot(self, snapshots: List[Dict[str, Any]], now_utc: datetime) -> Optional[Dict[str, Any]]:
        if not snapshots:
            return None
        ranked = sorted(snapshots, key=lambda item: self._score_btc_snapshot(item, now_utc), reverse=True)
        selected = ranked[0]
        logger.info("BTC 15m 选盘结果: %s (score=%.2f)", selected.get("slug"), self._score_btc_snapshot(selected, now_utc))
        return selected

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
            current_time = now_utc or datetime.now(timezone.utc)
            snapshots = await self.get_market_snapshots(current_time)
            return self._select_btc_snapshot(snapshots, current_time)
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

    async def get_signal_context(self) -> Optional[Dict[str, Any]]:
        source = Config.get("BTC_PRICE_SOURCE", "binance")
        if source == "binance":
            return await self._get_binance_signal_context()
        return await self.get_price()

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

    async def _get_binance_signal_context(self) -> Optional[Dict[str, Any]]:
        ticker_url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
        klines_url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=20"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(ticker_url, timeout=aiohttp.ClientTimeout(total=5)) as ticker_resp:
                    if ticker_resp.status != 200:
                        return None
                    ticker = await ticker_resp.json()

                async with session.get(klines_url, timeout=aiohttp.ClientTimeout(total=5)) as klines_resp:
                    if klines_resp.status != 200:
                        return None
                    klines = await klines_resp.json()
            except Exception as exc:
                logger.error("Binance signal API error: %s", exc)
                return None

        closes = [safe_float(item[4]) for item in klines if len(item) > 5]
        highs = [safe_float(item[2]) for item in klines if len(item) > 5]
        lows = [safe_float(item[3]) for item in klines if len(item) > 5]
        volumes = [safe_float(item[5]) for item in klines if len(item) > 5]
        if len(closes) < 16:
            return {
                "price": float(ticker["lastPrice"]),
                "change_24h": float(ticker["priceChangePercent"]),
                "source": "binance",
            }

        def pct_change(current: Optional[float], previous: Optional[float]) -> float:
            if current in (None, 0) or previous in (None, 0):
                return 0.0
            return ((current - previous) / previous) * 100

        price = safe_float(ticker.get("lastPrice"), closes[-1]) or closes[-1] or 0.0
        change_24h = safe_float(ticker.get("priceChangePercent"), 0.0) or 0.0
        change_1m = pct_change(closes[-1], closes[-2])
        change_3m = pct_change(closes[-1], closes[-4])
        change_5m = pct_change(closes[-1], closes[-6])
        change_15m = pct_change(closes[-1], closes[-16])
        range_high = max(item for item in highs[-15:] if item is not None)
        range_low = min(item for item in lows[-15:] if item is not None)
        range_span_pct = (((range_high - range_low) / range_low) * 100) if range_low else 0.0
        if range_high and range_low and range_high > range_low:
            range_position = (price - range_low) / (range_high - range_low)
        else:
            range_position = 0.5
        recent_volume = sum(item for item in volumes[-5:] if item is not None)
        prior_volume = sum(item for item in volumes[-10:-5] if item is not None)
        volume_ratio = (recent_volume / prior_volume) if prior_volume else 1.0

        direction = "flat"
        if change_3m > 0.08 and change_5m > 0.12:
            direction = "up"
        elif change_3m < -0.08 and change_5m < -0.12:
            direction = "down"

        return {
            "price": round(price, 2),
            "change_24h": round(change_24h, 2),
            "change_1m": round(change_1m, 4),
            "change_3m": round(change_3m, 4),
            "change_5m": round(change_5m, 4),
            "change_15m": round(change_15m, 4),
            "range_high_15m": round(range_high, 2) if range_high is not None else None,
            "range_low_15m": round(range_low, 2) if range_low is not None else None,
            "range_span_15m_pct": round(range_span_pct, 4),
            "range_position_15m": round(range_position, 4),
            "volume_ratio_5m": round(volume_ratio, 4),
            "direction_hint": direction,
            "source": "binance",
        }

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
