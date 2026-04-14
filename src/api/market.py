import aiohttp
import asyncio
import time
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from ..core.utils import safe_float, extract_market_slug
from ..core.config import (
    Config, BTC_PRICE_SOURCE, 
    POLYMARKET_WALLET_ADDRESS, 
    POLYMARKET_API_KEY
)

logger = logging.getLogger("market_api")

class PolymarketClient:
    """Polymarket API 客户端包装"""
    
    def __init__(self):
        self.BASE_URL = "https://gamma-api.polymarket.com"
        self.headers = {"Accept": "application/json"}

    async def get_market_snapshots(self, now_utc: datetime) -> List[dict]:
        """查找当前窗口内的候选 BTC 15 分钟盘口"""
        # 实现逻辑从 bot.py 迁移
        url = f"{self.BASE_URL}/markets?closed=false&limit=100"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        markets = data.get('data', []) if isinstance(data, dict) else data
                        # 过滤 BTC 15m 逻辑...
                        return [m for m in markets if "BTC" in m.get("question", "") and "15" in m.get("question", "")]
            except Exception as e:
                logger.error(f"Error fetching market snapshots: {e}")
        return []

    async def get_order_book(self, slug: str) -> Optional[dict]:
        """获取单个盘口的详细订单簿数据"""
        if not slug: return None
        url = f"https://clob.polymarket.com/book?token_id={slug}" # 简化，实际逻辑可能更复杂
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except:
                pass
        return None

    async def get_microstructure(self, market: dict) -> Dict[str, Any]:
        """获取盘口微观结构 (L2 深度)"""
        if not market: return {}
        slug = market.get("resolved_slug") or market.get("slug")
        if not slug:
            return {}
        book = await self.get_order_book(slug)
        return book or {}

class BTCDataprovider:
    """获取 BTC 价格数据"""
    
    async def get_price(self) -> Optional[Dict[str, Any]]:
        source = Config.get("BTC_PRICE_SOURCE", "binance")
        if source == "binance":
            return await self._get_binance_price()
        return await self._get_coingecko_price()

    async def _get_binance_price(self) -> Optional[Dict[str, Any]]:
        url = "https://api.binance.com/api/3/ticker/24hr?symbol=BTCUSDT"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "price": float(data['lastPrice']),
                            "change_24h": float(data['priceChangePercent']),
                            "source": "binance"
                        }
            except Exception as e:
                logger.error(f"Binance API error: {e}")
        return None

    async def _get_coingecko_price(self) -> Optional[Dict[str, Any]]:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        btc = data.get('bitcoin', {})
                        return {
                            "price": float(btc.get('usd', 0)),
                            "change_24h": float(btc.get('usd_24h_change', 0)),
                            "source": "coingecko"
                        }
            except Exception as e:
                logger.error(f"CoinGecko API error: {e}")
        return None
