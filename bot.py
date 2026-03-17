#!/usr/bin/env python3
"""
 Polymarket BTC Up/Down 5m 自动交易 Bot
 
 流程:
   BTC数据 → AI预测 → 概率判断 → Polymarket下单
   
 每5分钟运行一次
"""

import asyncio
import calendar
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
import requests
from dotenv import load_dotenv

# 状态文件路径
STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_status.json")
PAPER_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trade_state.json")
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trade_report.md")
CONTROL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_control.json")

def load_json_file(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json_file(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_trading_control():
    state = load_json_file(CONTROL_FILE, {})
    return {
        "trading_enabled": bool(state.get("trading_enabled", True)),
        "updated_at": state.get("updated_at"),
    }


def extract_market_slug(market_input: str) -> str:
    if not market_input:
        return ""
    if "polymarket.com/event/" in market_input:
        return market_input.split("polymarket.com/event/")[-1].split("#")[0].split("?")[0]
    return market_input.strip()


def parse_json_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []


def safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def iso_to_utc_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso_to_ts(value: str) -> int:
    return calendar.timegm(iso_to_utc_dt(value).utctimetuple())


def ts_to_iso(ts_value: int) -> str:
    return datetime.fromtimestamp(ts_value, tz=timezone.utc).isoformat()


def short_wallet(address: str) -> str:
    if not address or len(address) < 10:
        return "--"
    return f"{address[:6]}...{address[-4:]}"


def write_status(bot=None, market_info=None, btc_data=None, prediction=None, probabilities=None, decision=None, error=None, extra=None):
    """写入状态到文件"""
    try:
        status = {
            "running": True,
            "last_update": datetime.now().isoformat(),
            "btc_price": btc_data.get("price") if btc_data else None,
            "btc_change_24h": btc_data.get("change_24h") if btc_data else None,
            "ai_prediction": prediction,
            "yes_price": probabilities.get("yes_price") if probabilities else None,
            "no_price": probabilities.get("no_price") if probabilities else None,
            "outcomes": probabilities.get("outcomes") if probabilities else None,
            "decision_reason": probabilities.get("reason") if probabilities else None,
            "decision": decision,
            "total_trades": bot.stats.get("total_trades", 0) if bot else 0,
            "market": (market_info or {}).get("question") or (market_info or {}).get("title"),
            "error": error,
        }
        if extra:
            status.update(extra)
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"写入状态失败: {e}")

# ==================== 配置 ====================

load_dotenv()  # 加载 .env 文件

# Polymarket API 配置
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_WALLET_ADDRESS = os.getenv("POLYMARKET_WALLET_ADDRESS", "")

# 交易配置
BET_AMOUNT = float(os.getenv("BET_AMOUNT", "5"))        # 每次下注金额 (USDC)
MAX_BET_AMOUNT = float(os.getenv("MAX_BET_AMOUNT", "50"))  # 单笔最大
MIN_PROBABILITY_DIFF = float(os.getenv("MIN_PROBABILITY_DIFF", "0.1"))  # 最小概率差才下单
STOP_LOSS_ENABLED = bool(os.getenv("STOP_LOSS_ENABLED", "true").lower() == "true")
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "0.10"))  # 止损比例
TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "0.18"))
TRADING_MODE = os.getenv("TRADING_MODE", "paper").strip().lower()
PAPER_START_BALANCE = float(os.getenv("PAPER_START_BALANCE", "100"))
PAPER_BET_AMOUNT = float(os.getenv("PAPER_BET_AMOUNT", str(BET_AMOUNT)))
TIME_EXIT_SECONDS = int(os.getenv("TIME_EXIT_SECONDS", "45"))
PAPER_MIN_ENTRY_PRICE = float(os.getenv("PAPER_MIN_ENTRY_PRICE", "0.15"))
PAPER_MAX_ENTRY_PRICE = float(os.getenv("PAPER_MAX_ENTRY_PRICE", "0.60"))
PAPER_TAKE_PROFIT_USD = float(os.getenv("PAPER_TAKE_PROFIT_USD", "0.12"))
PAPER_POLL_INTERVAL_SECONDS = int(os.getenv("PAPER_POLL_INTERVAL_SECONDS", "15"))
PAPER_MAX_OPEN_POSITIONS = int(os.getenv("PAPER_MAX_OPEN_POSITIONS", "1"))
PAPER_MAX_SPREAD = float(os.getenv("PAPER_MAX_SPREAD", "0.06"))
PAPER_MIN_TOP_BOOK_SIZE = float(os.getenv("PAPER_MIN_TOP_BOOK_SIZE", "25"))
PAPER_MIN_MINUTES_TO_EXPIRY = int(os.getenv("PAPER_MIN_MINUTES_TO_EXPIRY", "3"))
PAPER_MAX_NEW_POSITIONS_PER_CYCLE = int(os.getenv("PAPER_MAX_NEW_POSITIONS_PER_CYCLE", "1"))
PAPER_MARKET_INTERVAL_MINUTES = int(os.getenv("PAPER_MARKET_INTERVAL_MINUTES", "15"))
PAPER_FORWARD_SLOT_COUNT = int(os.getenv("PAPER_FORWARD_SLOT_COUNT", "8"))
PAPER_WALLET_LABEL = os.getenv("PAPER_WALLET_LABEL", "LOCAL-SIM")

# BTC 配置
BTC_PRICE_SOURCE = os.getenv("BTC_PRICE_SOURCE", "binance")  # binance 或 coingecko
NY_TZ = ZoneInfo("America/New_York")

# AI 交易配置（OpenAI 兼容接口）
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_DECISION_INTERVAL_SECONDS = int(os.getenv("AI_DECISION_INTERVAL_SECONDS", "180"))
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai_compatible")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "") or os.getenv("MINIMAX_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.2"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "700"))

# Market ID (需要你自己填)
# 可以填: 
#   - 市场 slug (如 "btc-updown-5m-1773289200")
#   - 完整 URL (如 "https://polymarket.com/event/btc-updown-5m-1773289200")
#   - Condition ID (如 "0xabc123...")
BTC_UPDOWN_MARKET_ID = os.getenv("BTC_UPDOWN_MARKET_ID", "")


async def get_condition_id_from_market(client, market_input: str) -> Optional[dict]:
    """从市场 URL/slug 获取 Condition ID"""
    try:
        # 优先检查: 如果输入的是 condition_id (0x开头，66位)，直接使用
        if market_input.startswith("0x") and len(market_input) == 66:
            print(f"🔍 使用 Condition ID: {market_input}")
            return {'condition_id': market_input, 'question': 'Manual Condition ID'}
        
        # 提取 slug
        slug = market_input
        if "polymarket.com/event/" in market_input:
            # 从 URL 提取 slug
            slug = market_input.split("polymarket.com/event/")[-1].split("#")[0].split("?")[0]
        
        print(f"🔍 查找市场: {slug}")
        
        # 尝试通过 API 获取市场信息
        async with aiohttp.ClientSession() as session:
            # 方法1: 通过 eventSlug 查询
            url = f"{client.BASE_URL}/markets"
            params = {"eventSlug": slug}
            
            async with session.get(url, params=params, headers=client.headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    markets = data.get('data', []) if isinstance(data, dict) else data
                    
                    # 优先找 accepting_orders 的市场
                    for m in markets:
                        if m.get('accepting_orders') or m.get('active'):
                            return {
                                'condition_id': m.get('condition_id'),
                                'question': m.get('question'),
                                'market_slug': m.get('market_slug'),
                            }
                    
                    # 返回第一个
                    if markets:
                        return {
                            'condition_id': markets[0].get('condition_id'),
                            'question': markets[0].get('question'),
                            'market_slug': markets[0].get('market_slug'),
                        }
            
            # 方法2: 通过 event 查询
            url2 = f"{client.BASE_URL}/markets"
            params2 = {"event": slug}
            
            async with session.get(url2, params=params2, headers=client.headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    markets = data.get('data', []) if isinstance(data, dict) else data
                    
                    for m in markets:
                        if m.get('accepting_orders') or m.get('active'):
                            return {
                                'condition_id': m.get('condition_id'),
                                'question': m.get('question'),
                                'market_slug': m.get('market_slug'),
                            }
                    
                    if markets:
                        return {
                            'condition_id': markets[0].get('condition_id'),
                            'question': markets[0].get('question'),
                            'market_slug': markets[0].get('market_slug'),
                        }
            
            # 方法3: 搜索包含 slug 关键词的市场
            url3 = f"{client.BASE_URL}/markets"
            params3 = {"limit": "500", "closed": "false"}
            
            async with session.get(url3, params=params3, headers=client.headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    markets = data.get('data', []) if isinstance(data, dict) else data
                    
                    # 模糊匹配 slug
                    for m in markets:
                        market_slug = m.get('market_slug', '').lower()
                        question = m.get('question', '').lower()
                        if slug.lower() in market_slug or slug.lower() in question:
                            return {
                                'condition_id': m.get('condition_id'),
                                'question': m.get('question'),
                                'market_slug': m.get('market_slug'),
                            }
            
            # 方法4: 如果输入的是 condition_id，直接返回
            if market_input.startswith("0x") and len(market_input) == 66:
                return {'condition_id': market_input, 'question': 'Unknown'}
                
        print(f"⚠️ 未找到市场: {slug}")
        return None
    except Exception as e:
        print(f"获取 Condition ID 失败: {e}")
        return None

# ==================== 辅助函数 ====================

async def find_active_btc_5m_market(client) -> Optional[dict]:
    """查找当前活跃的 BTC 5m 市场"""
    try:
        # 尝试多个 API 端点来查找
        endpoints = [
            f"{client.BASE_URL}/markets?closed=false&limit=1000",
            f"{client.BASE_URL}/markets?limit=1000",
        ]
        
        for url in endpoints:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=client.headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        markets = data.get('data', []) if isinstance(data, dict) else data
                        
                        # 先找接受订单的市场
                        for m in markets:
                            if not m.get('accepting_orders'):
                                continue
                            q = m.get('question', '').lower()
                            slug = m.get('market_slug', '').lower()
                            
                            # 匹配 BTC 5m 市场
                            if (('btc' in q or 'bitcoin' in q) and 
                                ('5m' in q or '5min' in q or '5 min' in q or 'up' in q or 'down' in q)):
                                return {
                                    'condition_id': m.get('condition_id'),
                                    'question': m.get('question'),
                                    'market_slug': m.get('market_slug'),
                                    'active': m.get('active'),
                                    'accepting_orders': m.get('accepting_orders')
                                }
                            
                            if 'btc' in slug and '5m' in slug:
                                return {
                                    'condition_id': m.get('condition_id'),
                                    'question': m.get('question'),
                                    'market_slug': m.get('market_slug'),
                                    'active': m.get('active'),
                                    'accepting_orders': m.get('accepting_orders')
                                }
                        
                        # 如果没找到接受的，找活跃的
                        for m in markets:
                            if not m.get('active'):
                                continue
                            q = m.get('question', '').lower()
                            slug = m.get('market_slug', '').lower()
                            
                            if (('btc' in q or 'bitcoin' in q) and 
                                ('5m' in q or '5min' in q or '5 min' in q or 'up' in q or 'down' in q)):
                                return {
                                    'condition_id': m.get('condition_id'),
                                    'question': m.get('question'),
                                    'market_slug': m.get('market_slug'),
                                    'active': m.get('active'),
                                    'accepting_orders': m.get('accepting_orders')
                                }
            except Exception as e:
                print(f"  尝试端点失败: {e}")
                continue
                
        return None
    except Exception as e:
        print(f"查找 BTC 5m 市场失败: {e}")
        return None

# ==================== API 客户端 ====================

class PolymarketClient:
    """Polymarket API 客户端"""
    
    BASE_URL = "https://clob.polymarket.com"
    
    def __init__(self, api_key: str, private_key: str, wallet_address: str):
        self.api_key = api_key
        self.private_key = private_key
        self.wallet_address = wallet_address
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    
    async def get_markets(self, event_id: str = None):
        """获取市场信息"""
        url = f"{self.BASE_URL}/markets"
        params = {}
        if event_id:
            params["event_id"] = event_id
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=self.headers) as resp:
                return await resp.json()
    
    async def get_order_book(self, condition_id: str):
        """获取订单簿"""
        url = f"{self.BASE_URL}/orderbook/{condition_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                return await resp.json()
    
    async def get_fills(self, condition_id: str):
        """获取成交记录"""
        url = f"{self.BASE_URL}/fills"
        params = {"conditionId": condition_id}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=self.headers) as resp:
                return await resp.json()
    
    async def place_order(self, condition_id: str, side: str, amount: float, price: float = None):
        """
        下单
        side: "Buy" 或 "Sell"
        """
        order_data = {
            "assetId": condition_id,
            "side": side,
            "size": str(amount),
            "price": str(price) if price else "0.5",  # 市价用 0.5
            "walletAddress": self.wallet_address
        }
        
        url = f"{self.BASE_URL}/orders"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=order_data, headers=self.headers) as resp:
                return await resp.json()
    
    async def cancel_orders(self, order_ids: list):
        """取消订单"""
        url = f"{self.BASE_URL}/orders"
        
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, json={"orderIDs": order_ids}, headers=self.headers) as resp:
                return await resp.json()


class BTCDataprovider:
    """BTC 价格数据源"""
    
    @staticmethod
    def get_price_binance() -> Optional[dict]:
        """从 Binance 获取 BTC 价格"""
        try:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            return {
                "price": float(data["price"]),
                "source": "binance",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"❌ 获取 Binance BTC 价格失败: {e}")
            return None
    
    @staticmethod
    def get_price_coingecko() -> Optional[dict]:
        """从 CoinGecko 获取 BTC 价格"""
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            return {
                "price": data["bitcoin"]["usd"],
                "source": "coingecko",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"❌ 获取 CoinGecko BTC 价格失败: {e}")
            return None
    
    @staticmethod
    def get_price_with_change() -> Optional[dict]:
        """获取价格 + 24h 变化"""
        try:
            url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            return {
                "price": float(data["lastPrice"]),
                "change_24h": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
                "source": "binance",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"❌ 获取 BTC 24h 数据失败: {e}")
            return None


class AIDecisionEngine:
    """使用 OpenAI 兼容接口做结构化交易判断；无密钥时自动回退到规则策略。"""

    def __init__(self):
        self.enabled = AI_ENABLED
        self.base_url = AI_BASE_URL.rstrip("/")
        self.api_key = AI_API_KEY
        self.model = AI_MODEL
        self.temperature = AI_TEMPERATURE
        self.max_tokens = AI_MAX_TOKENS

    def parse_json_content(self, content: str) -> dict:
        raw = (content or "").strip()
        if not raw:
            return {}

        think_stripped = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        candidates = [think_stripped, raw]

        for candidate in candidates:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except Exception:
                pass

            match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass

        raise ValueError(f"模型输出不是有效 JSON: {raw[:300]}")

    def build_rule_fallback(self, payload: dict, fallback_reason: str) -> dict:
        btc = payload.get("btc", {})
        daily_open = safe_float(payload.get("daily_open"), 0.0) or 0.0
        current_price = safe_float(btc.get("price"), 0.0) or 0.0
        prediction = "HOLD"
        action = "HOLD"
        if current_price > daily_open:
            prediction = "UP"
            action = "BUY"
        elif current_price < daily_open:
            prediction = "DOWN"
            action = "BUY"

        return {
            "prediction": prediction,
            "action": action,
            "confidence": 0.35,
            "reasoning": f"AI 不可用，回退为规则策略：现价 {current_price:,.2f} 与今开 {daily_open:,.2f} 比较。{fallback_reason}",
            "key_factors": [
                f"BTC 现价 {current_price:,.2f}",
                f"今开 {daily_open:,.2f}",
                f"24h 涨跌 {safe_float(btc.get('change_24h'), 0.0) or 0.0:+.2f}%",
            ],
            "risk_flags": ["当前为规则回退，不是真实 LLM 输出"],
            "close_positions": False,
            "source": "fallback",
        }

    def build_prompt(self, payload: dict) -> tuple[str, str]:
        system = (
            "你是一个谨慎的 Polymarket BTC 短线纸上交易分析器。"
            "你只能输出严格 JSON，不要输出 markdown。"
            "目标：每 3 分钟评估一次是否 BUY / SELL / HOLD。"
            "BUY 表示允许按目标方向寻找可交易盘口开仓；SELL 表示建议把当前持仓平掉；HOLD 表示观望。"
            "prediction 只能是 UP、DOWN、HOLD。action 只能是 BUY、SELL、HOLD。"
            "必须提供 reasoning、key_factors、risk_flags、confidence。"
            "如果信号不够强，宁可 HOLD。"
        )
        user = json.dumps(payload, ensure_ascii=False)
        return system, user

    def call_model(self, payload: dict) -> dict:
        if not self.enabled:
            return self.build_rule_fallback(payload, "AI_ENABLED=false")
        if not self.api_key:
            return self.build_rule_fallback(payload, "未配置 AI_API_KEY")

        system, user = self.build_prompt(payload)
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}").strip()
        parsed = self.parse_json_content(content)
        return {
            "prediction": str(parsed.get("prediction", "HOLD")).upper(),
            "action": str(parsed.get("action", "HOLD")).upper(),
            "confidence": round(float(parsed.get("confidence", 0.0)), 4),
            "reasoning": str(parsed.get("reasoning", ""))[:1200],
            "key_factors": [str(x)[:220] for x in (parsed.get("key_factors") or [])[:6]],
            "risk_flags": [str(x)[:220] for x in (parsed.get("risk_flags") or [])[:6]],
            "close_positions": bool(parsed.get("close_positions", str(parsed.get("action", "")).upper() == "SELL")),
            "source": "llm",
        }


class TradingBot:
    """交易 Bot 主类"""
    
    def __init__(self):
        self.poly_client = PolymarketClient(
            api_key=POLYMARKET_API_KEY,
            private_key=POLYMARKET_PRIVATE_KEY,
            wallet_address=POLYMARKET_WALLET_ADDRESS
        )
        self.btc_provider = BTCDataprovider()
        self.ai_predictor = AIPredictor()
        
        # 历史数据
        self.price_history = []
        
        # 交易统计
        self.stats = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_profit": 0.0
        }
    
    async def get_market_info(self, market_id: str) -> Optional[dict]:
        """获取市场详情和当前概率"""
        try:
            # 这里需要根据实际 API 调整
            # Polymarket 的 market ID 格式通常是 uuid
            url = f"https://clob.polymarket.com/markets/{market_id}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except Exception as e:
            print(f"❌ 获取市场信息失败: {e}")
            return None
    
    async def get_current_probabilities(self, condition_id: str) -> Optional[dict]:
        """获取当前 Yes/No 概率"""
        try:
            # 先尝试用 market API 获取价格
            async with aiohttp.ClientSession() as session:
                url = f"{self.poly_client.BASE_URL}/markets/{condition_id}"
                async with session.get(url, headers=self.poly_client.headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        market = await resp.json()
                        tokens = market.get('tokens', [])
                        
                        yes_price = None
                        no_price = None
                        
                        for t in tokens:
                            outcome = t.get('outcome', '').lower()
                            price = float(t.get('price', 0))
                            if 'yes' in outcome:
                                yes_price = price
                            elif 'no' in outcome:
                                no_price = price
                        
                        if yes_price is not None and no_price is not None:
                            return {
                                "yes_price": yes_price,
                                "no_price": no_price,
                            }
            
            # 如果 market API 失败，尝试 orderbook
            orderbook = await self.poly_client.get_order_book(condition_id)
            
            # 计算最佳买卖价
            yes_bids = orderbook.get("bids", [])  # 买 Yes 的单
            yes_asks = orderbook.get("asks", [])  # 卖 Yes 的单
            
            if yes_bids and yes_asks:
                best_bid = float(yes_bids[0][0])  # 最高买价
                best_ask = float(yes_asks[0][0])  # 最低卖价
                mid_price = (best_bid + best_ask) / 2
                
                return {
                    "yes_price": mid_price,
                    "no_price": 1 - mid_price,
                    "best_bid": best_bid,
                    "best_ask": best_ask
                }
        except Exception as e:
            print(f"❌ 获取概率失败: {e}")
        return None
    
    async def should_trade(self, prediction: str, probabilities: dict) -> tuple:
        """
        判断是否应该下单
        返回: (should_trade: bool, side: str, reason: str)
        """
        if not probabilities:
            return False, "", "无概率数据"
        
        yes_price = probabilities.get("yes_price", 0.5)
        
        # 概率判断
        if prediction == "UP":
            # 预测涨 -> 买 Yes
            if yes_price < 0.5 - MIN_PROBABILITY_DIFF:
                # 市场价格比 50% 低，有价值
                return True, "Buy", f"Yes 价格 {yes_price:.2%} 有价值"
            elif yes_price > 0.5 + MIN_PROBABILITY_DIFF:
                # 市场价格太高，不买
                return False, "", f"Yes 价格 {yes_price:.2%} 太高"
            else:
                return False, "", f"Yes 价格 {yes_price:.2%} 无明显价值"
        
        elif prediction == "DOWN":
            # 预测跌 -> 买 No
            no_price = probabilities.get("no_price", 0.5)
            if no_price < 0.5 - MIN_PROBABILITY_DIFF:
                return True, "Buy", f"No 价格 {no_price:.2%} 有价值"
            elif no_price > 0.5 + MIN_PROBABILITY_DIFF:
                return False, "", f"No 价格 {no_price:.2%} 太高"
            else:
                return False, "", f"No 价格 {no_price:.2%} 无明显价值"
        
        return False, "", "HOLD 信号"
    
    async def execute_trade(self, side: str, amount: float, condition_id: str):
        """执行交易"""
        try:
            # 先获取当前最佳价格
            probs = await self.get_current_probabilities(condition_id)
            if not probs:
                print("❌ 无法获取价格，跳过下单")
                return False
            
            price = probs.get("best_ask", 0.5) if side == "Buy" else probs.get("best_bid", 0.5)
            
            print(f"📝 下单: {side} Yes, 金额: ${amount}, 价格: {price:.2%}")
            
            # 实际下单
            result = await self.poly_client.place_order(
                condition_id=condition_id,
                side=side,
                amount=amount,
                price=price
            )
            
            print(f"✅ 下单结果: {result}")
            self.stats["total_trades"] += 1
            return True
            
        except Exception as e:
            print(f"❌ 下单失败: {e}")
            return False
    
    async def run_cycle(self, market_id: str, condition_id: str):
        """运行一次交易循环"""
        print(f"\n{'='*50}")
        print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始交易循环")
        print(f"{'='*50}")
        
        # 1. 获取 BTC 数据
        print("\n📊 Step 1: 获取 BTC 数据...")
        btc_data = self.btc_provider.get_price_with_change()
        if btc_data:
            print(f"   BTC 价格: ${btc_data['price']:,.2f}")
            print(f"   24h 变化: {btc_data['change_24h']:+.2f}%")
            
            # 记录历史
            self.price_history.append(btc_data)
            if len(self.price_history) > 100:
                self.price_history.pop(0)
        
        # 2. AI 预测
        print("\n🔮 Step 2: AI 预测...")
        prediction = await self.ai_predictor.predict(btc_data, self.price_history)
        
        # 3. 获取市场概率
        print("\n📈 Step 3: 获取 Polymarket 概率...")
        probabilities = await self.get_current_probabilities(condition_id)
        if probabilities:
            print(f"   Yes 价格: {probabilities['yes_price']:.2%}")
            print(f"   No 价格: {probabilities['no_price']:.2%}")
        
        # 4. 判断是否交易
        print("\n🎯 Step 4: 判断是否交易...")
        should_trade, side, reason = await self.should_trade(prediction, probabilities)
        trading_enabled = load_trading_control().get("trading_enabled", True)
        if should_trade and not trading_enabled:
            should_trade = False
            reason = "交易已关闭，当前不会自动新开仓"
        print(f"   决策: {reason}")
        
        # 5. 执行交易
        if should_trade:
            print(f"\n💰 Step 5: 执行交易...")
            # 判断买 Yes 还是 No
            # prediction == UP -> 买 Yes
            # prediction == DOWN -> 买 No (即卖 Yes)
            actual_side = "Buy" if prediction == "UP" else "Sell"
            
            await self.execute_trade(actual_side, BET_AMOUNT, condition_id)
        else:
            print(f"\n⏭️ 跳过交易: {reason}")
        
        # 6. 显示统计
        print(f"\n📊 统计: 总交易 {self.stats['total_trades']} 笔")
        
        # 7. 写入状态文件
        decision = "BUY" if should_trade else ("HOLD" if reason else "NONE")
        write_status(
            self,
            None,
            btc_data,
            prediction,
            probabilities,
            decision,
            extra={
                "decision_reason": reason,
                "trading_enabled": trading_enabled,
            },
        )
    
    async def run_forever(self, interval_seconds: int = 300):
        """持续运行"""
        market_input = BTC_UPDOWN_MARKET_ID
        
        print(f"""
🤖 Polymarket BTC 5m 交易 Bot 启动!
        
配置:
  - 下注金额: ${BET_AMOUNT}
  - 最大单笔: ${MAX_BET_AMOUNT}
  - 最小概率差: {MIN_PROBABILITY_DIFF:.1%}
  - 止损: {'开启' if STOP_LOSS_ENABLED else '关闭'}
  - 运行间隔: {interval_seconds} 秒
  - 市场: {market_input}
        
按 Ctrl+C 停止
        """)
        
        if not market_input:
            print("❌ 未配置市场 ID!")
            print("   在 .env 中设置 BTC_UPDOWN_MARKET_ID")
            print("   可以是: URL、slug 或 Condition ID")
            return
        
        current_condition_id = None
        
        while True:
            try:
                # 获取/刷新 Condition ID
                market_info = await get_condition_id_from_market(self.poly_client, market_input)
                
                if market_info:
                    condition_id = market_info['condition_id']
                    
                    if condition_id != current_condition_id:
                        current_condition_id = condition_id
                        print(f"\n🆕 市场已连接: {market_info.get('question', 'Unknown')}")
                        print(f"   Condition ID: {condition_id}")
                    
                    await self.run_cycle(None, condition_id)
                else:
                    print(f"\n⚠️ 无法获取市场信息: {market_input}")
                    
            except Exception as e:
                print(f"❌ 循环出错: {e}")
            
            print(f"\n😴 等待 {interval_seconds} 秒...")
            await asyncio.sleep(interval_seconds)


class PaperReplayBot:
    """保留原有的 5 分钟虚拟回放模式。"""

    GAMMA_BASE = "https://gamma-api.polymarket.com"
    CLOB_BASE = "https://clob.polymarket.com"

    def __init__(self):
        self.market_input = BTC_UPDOWN_MARKET_ID
        self.paper_balance = PAPER_START_BALANCE
        self.stats = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_profit": 0.0,
        }

    def get_market_snapshot(self) -> dict:
        slug = extract_market_slug(self.market_input)
        if not slug:
            raise ValueError("未配置 BTC_UPDOWN_MARKET_ID")

        resp = requests.get(f"{self.GAMMA_BASE}/markets/slug/{slug}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        data["resolved_slug"] = slug
        return data

    def get_price_histories(self, market: dict) -> dict:
        outcomes = [item.upper() for item in parse_json_list(market.get("outcomes"))]
        token_ids = parse_json_list(market.get("clobTokenIds"))
        end_ts = iso_to_ts(market["endDate"])
        start_ts = max(end_ts - 600, end_ts - 1800)

        histories = {}
        for outcome, token_id in zip(outcomes, token_ids):
            url = (
                f"{self.CLOB_BASE}/prices-history?market={token_id}"
                f"&startTs={start_ts}&endTs={end_ts}&fidelity=1"
            )
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            histories[outcome] = resp.json().get("history", [])
        return histories

    def find_trade_signal(self, histories: dict) -> dict:
        outcomes = list(histories.keys())
        points = min(len(histories[outcome]) for outcome in outcomes)
        if points < 4:
            raise ValueError("价格历史不足，无法生成虚拟交易")

        for idx in range(3, points - 1):
            rolling_avg = {}
            for outcome in outcomes:
                window = histories[outcome][idx - 3:idx]
                rolling_avg[outcome] = sum(item["p"] for item in window) / len(window)

            dominant = max(rolling_avg, key=rolling_avg.get)
            other = [item for item in outcomes if item != dominant][0]
            lead = rolling_avg[dominant] - rolling_avg[other]
            prev_price = histories[dominant][idx - 1]["p"]
            current_price = histories[dominant][idx]["p"]
            dislocation = prev_price - current_price

            if lead >= 0.03 and dislocation >= 0.10 and 0.20 < current_price < 0.80:
                return {
                    "entry_index": idx,
                    "dominant_outcome": dominant,
                    "other_outcome": other,
                    "entry_price": current_price,
                    "prior_price": prev_price,
                    "lead": round(lead, 4),
                    "dislocation": round(dislocation, 4),
                    "entry_ts": histories[dominant][idx]["t"],
                    "other_price": histories[other][idx]["p"],
                    "reason": (
                        f"{dominant} 在前 3 个报价窗口维持优势，但当前出现 "
                        f"{dislocation:.1%} 的快速回撤，适合做同向回归纸上交易"
                    ),
                }

        raise ValueError("未找到满足条件的 5 分钟虚拟交易信号")

    def build_replay(self, market: dict, histories: dict) -> dict:
        signal = self.find_trade_signal(histories)
        outcome = signal["dominant_outcome"]
        other = signal["other_outcome"]
        entry_idx = signal["entry_index"]
        entry_price = signal["entry_price"]
        stake = round(min(PAPER_BET_AMOUNT, MAX_BET_AMOUNT, self.paper_balance), 2)
        shares = round(stake / entry_price, 6)
        take_profit_price = round(min(entry_price * (1 + TAKE_PROFIT_PERCENT), 0.99), 4)
        stop_loss_price = round(max(entry_price * (1 - STOP_LOSS_PERCENT), 0.01), 4)

        exit_price = None
        exit_reason = "TIME_EXIT"
        exit_ts = iso_to_ts(market["endDate"])
        observed_exit_price = None

        for idx in range(entry_idx + 1, len(histories[outcome])):
            current_price = histories[outcome][idx]["p"]
            current_ts = histories[outcome][idx]["t"]
            if current_price >= take_profit_price:
                exit_price = take_profit_price
                observed_exit_price = current_price
                exit_ts = current_ts
                exit_reason = "TAKE_PROFIT"
                break

            if STOP_LOSS_ENABLED and current_price <= stop_loss_price:
                exit_price = stop_loss_price
                observed_exit_price = current_price
                exit_ts = current_ts
                exit_reason = "STOP_LOSS"
                break

            if iso_to_ts(market["endDate"]) - current_ts <= TIME_EXIT_SECONDS:
                exit_price = current_price
                observed_exit_price = current_price
                exit_ts = current_ts
                exit_reason = "TIME_EXIT"
                break

        if exit_price is None:
            outcome_prices = [float(item) for item in parse_json_list(market.get("outcomePrices"))]
            outcomes = [item.upper() for item in parse_json_list(market.get("outcomes"))]
            outcome_index = outcomes.index(outcome)
            exit_price = outcome_prices[outcome_index]
            observed_exit_price = exit_price
            exit_reason = "RESOLUTION"

        profit = round(shares * exit_price - stake, 4)
        roi_percent = round((profit / stake) * 100, 2) if stake else 0.0
        self.paper_balance = round(self.paper_balance + profit, 4)

        self.stats["total_trades"] = 1
        if profit >= 0:
            self.stats["winning_trades"] = 1
        else:
            self.stats["losing_trades"] = 1
        self.stats["total_profit"] = profit

        entry_time = ts_to_iso(signal["entry_ts"])
        exit_time = ts_to_iso(exit_ts)
        question = market.get("question", "Polymarket 5 分钟市场")

        trades = [
            {
                "id": "paper-entry",
                "created_at": entry_time,
                "side": "BUY",
                "outcome": outcome,
                "amount": f"${stake:.2f} / {shares:.4f} shares",
                "price": round(entry_price, 4),
                "status": "OPENED",
                "market": question,
                "note": signal["reason"],
            },
            {
                "id": "paper-exit",
                "created_at": exit_time,
                "side": "SELL",
                "outcome": outcome,
                "amount": f"${stake + profit:.2f}",
                "price": round(exit_price, 4),
                "status": exit_reason,
                "market": question,
                "note": (
                    f"{exit_reason}，观测到的成交区间价格 {observed_exit_price:.4f}，"
                    f"实现盈亏 {profit:+.4f} USDC"
                ),
            },
        ]

        orders = [
            {
                "side": "BUY",
                "outcome": outcome,
                "price": round(entry_price, 4),
                "size": f"{shares:.4f}",
                "tp": take_profit_price,
                "sl": stop_loss_price,
                "status": exit_reason,
            }
        ]

        report = {
            "mode": "paper_replay",
            "wallet": POLYMARKET_WALLET_ADDRESS,
            "market_slug": market.get("resolved_slug"),
            "market_question": question,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "observed_exit_price": round(observed_exit_price, 4),
            "take_profit_percent": TAKE_PROFIT_PERCENT,
            "stop_loss_percent": STOP_LOSS_PERCENT,
            "stake": stake,
            "shares": round(shares, 4),
            "profit": profit,
            "roi_percent": roi_percent,
            "result": "WIN" if profit >= 0 else "LOSS",
            "strategy": "Dominant-side dip re-entry",
            "reason": signal["reason"],
            "other_outcome": other,
            "other_price_at_entry": round(signal["other_price"], 4),
            "ending_balance": self.paper_balance,
        }

        return {
            "trades": trades,
            "orders": orders,
            "positions": [],
            "report": report,
            "summary": {
                "starting_balance": PAPER_START_BALANCE,
                "ending_balance": self.paper_balance,
                "realized_pnl": profit,
                "unrealized_pnl": 0.0,
                "trade_count": 1,
                "win_rate": 1.0 if profit >= 0 else 0.0,
            },
            "probabilities": {
                "yes_price": round(signal["other_price"], 4),
                "no_price": round(entry_price, 4),
                "outcomes": [other.title(), outcome.title()],
                "reason": signal["reason"],
            },
        }

    def write_report(self, replay: dict, market: dict):
        report = replay["report"]
        lines = [
            "# Polymarket 5分钟虚拟交易报告",
            "",
            f"- 生成时间: {datetime.now(timezone.utc).isoformat()}",
            f"- 市场: {report['market_question']}",
            f"- 市场链接: https://polymarket.com/event/{report['market_slug']}",
            f"- 模式: {report['mode']}",
            f"- 钱包参考: {short_wallet(report['wallet'])}",
            f"- 策略: {report['strategy']}",
            f"- 入场: {report['entry_time']} · 买入 {replay['trades'][0]['outcome']} @ {report['entry_price']:.4f}",
            f"- 离场: {report['exit_time']} · {report['result']} · {replay['trades'][1]['status']} @ {report['exit_price']:.4f}",
            f"- 止盈 / 止损: {report['take_profit_percent']:.0%} / {report['stop_loss_percent']:.0%}",
            f"- 仓位: ${report['stake']:.2f} ({report['shares']:.4f} shares)",
            f"- 结果: {report['profit']:+.4f} USDC ({report['roi_percent']:+.2f}%)",
            f"- 期末纸上余额: ${report['ending_balance']:.4f}",
            "",
            "## 执行逻辑",
            "",
            f"{report['reason']}。",
            "",
            f"该市场在 {market['endDate']} 收盘；本次回放使用 Polymarket 官方价格历史数据生成，"
            "不是实际下单。",
        ]

        with open(REPORT_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")

    async def run(self):
        market = self.get_market_snapshot()
        histories = self.get_price_histories(market)
        replay = self.build_replay(market, histories)

        paper_state = {
            "mode": "paper_replay",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "market": {
                "slug": market.get("resolved_slug"),
                "question": market.get("question"),
                "end_date": market.get("endDate"),
                "closed": market.get("closed"),
                "accepting_orders": market.get("acceptingOrders"),
            },
            "wallet": POLYMARKET_WALLET_ADDRESS,
            "trades": replay["trades"],
            "positions": replay["positions"],
            "orders": replay["orders"],
            "summary": replay["summary"],
            "report": replay["report"],
        }
        save_json_file(PAPER_STATE_FILE, paper_state)
        self.write_report(replay, market)

        write_status(
            market_info={"question": market.get("question")},
            prediction=replay["trades"][0]["outcome"],
            probabilities=replay["probabilities"],
            decision="BUY",
            extra={
                "market_slug": market.get("resolved_slug"),
                "trading_mode": "paper_replay",
                "total_trades": replay["summary"]["trade_count"],
                "paper_profit": replay["report"]["profit"],
                "paper_roi_percent": replay["report"]["roi_percent"],
                "paper_result": replay["report"]["result"],
            },
        )

        print("\n📘 虚拟交易回放已生成")
        print(f"   市场: {market.get('question')}")
        print(f"   结果: {replay['report']['profit']:+.4f} USDC ({replay['report']['roi_percent']:+.2f}%)")
        print(f"   报告: {REPORT_FILE}")


class ContinuousPaperTradingBot:
    """按日 K 方向交易当日 BTC 15 分钟盘的持续纸上交易器。"""

    GAMMA_BASE = "https://gamma-api.polymarket.com"
    CLOB_BASE = "https://clob.polymarket.com"

    def __init__(self):
        self.wallet_label = PAPER_WALLET_LABEL or short_wallet(POLYMARKET_WALLET_ADDRESS) or "LOCAL-SIM"
        self.state = self.load_or_init_state()
        self.stats = self.state["stats"]
        self.ai_engine = AIDecisionEngine()
        self.last_ai_signal = self.state.get("last_signal", {})

    def load_or_init_state(self) -> dict:
        state = load_json_file(PAPER_STATE_FILE, {})
        if state.get("mode") != "paper_live":
            state = self.build_default_state()

        state.setdefault("cash_balance", state.get("summary", {}).get("cash_balance", PAPER_START_BALANCE))
        state.setdefault("positions", [])
        state.setdefault("orders", [])
        state.setdefault("trades", [])
        state.setdefault("closed_markets", [])
        state.setdefault("ai_history", [])
        state.setdefault(
            "stats",
            {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_profit": 0.0,
            },
        )
        state.setdefault("summary", {})
        state.setdefault("report", {})
        state.setdefault("market", {})
        state.setdefault("last_signal", {})
        state.setdefault("session_started_at", state.get("generated_at") or datetime.now(timezone.utc).isoformat())
        return state

    def build_default_state(self) -> dict:
        started_at = datetime.now(timezone.utc).isoformat()
        return {
            "mode": "paper_live",
            "generated_at": started_at,
            "session_started_at": started_at,
            "wallet": self.wallet_label,
            "cash_balance": round(PAPER_START_BALANCE, 4),
            "positions": [],
            "orders": [],
            "trades": [],
            "closed_markets": [],
            "ai_history": [],
            "stats": {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_profit": 0.0,
            },
            "summary": {
                "starting_balance": PAPER_START_BALANCE,
                "session_started_at": started_at,
                "cash_balance": PAPER_START_BALANCE,
                "reserved_balance": 0.0,
                "ending_balance": PAPER_START_BALANCE,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "trade_count": 0,
                "win_rate": 0.0,
                "open_positions": 0,
            },
            "report": {},
            "market": {},
            "last_signal": {},
        }

    def build_decision_id(self, now_utc: datetime) -> str:
        return f"AI-{now_utc.strftime('%m%d-%H%M%S')}"

    def build_ai_candidate_digest(self, candidates: list) -> list:
        digest = []
        for item in (candidates or [])[:4]:
            digest.append(
                {
                    "question": item.get("question"),
                    "slug": item.get("slug"),
                    "minutes_to_expiry": item.get("minutes_to_expiry"),
                    "accepting_orders": item.get("accepting_orders"),
                    "up": item.get("UP") or {},
                    "down": item.get("DOWN") or {},
                }
            )
        return digest

    def upsert_ai_history_entry(self, signal: Optional[dict], decision: str, reason: str, focus_market: Optional[dict] = None):
        if not signal:
            return
        decision_id = signal.get("decision_id")
        if not decision_id:
            return

        history = self.state.setdefault("ai_history", [])
        entry = None
        for item in history:
            if item.get("decision_id") == decision_id:
                entry = item
                break

        if entry is None:
            entry = {
                "decision_id": decision_id,
                "generated_at": signal.get("generated_at"),
                "linked_trades": [],
            }
            history.insert(0, entry)

        entry.update(
            {
                "generated_at": signal.get("generated_at"),
                "prediction": signal.get("prediction"),
                "action": signal.get("action"),
                "decision": decision,
                "confidence": signal.get("ai_confidence"),
                "model": signal.get("ai_model"),
                "source": signal.get("ai_source"),
                "reasoning": signal.get("reason"),
                "thought_markdown": signal.get("ai_thought_markdown"),
                "key_factors": signal.get("ai_key_factors", []),
                "risk_flags": signal.get("ai_risk_flags", []),
                "candidate_markets": signal.get("ai_candidate_markets", []),
                "execution_summary": reason,
                "focus_market": (focus_market or {}).get("question"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        entry["linked_trades"] = [
            {
                "trade_id": trade.get("id"),
                "created_at": trade.get("created_at"),
                "side": trade.get("side"),
                "outcome": trade.get("outcome"),
                "price": trade.get("price"),
                "status": trade.get("status"),
                "market": trade.get("market"),
                "realized_profit": trade.get("realized_profit"),
                "amount_display": trade.get("amount_display"),
            }
            for trade in self.state.get("trades", [])
            if trade.get("ai_decision_id") == decision_id
        ][:12]
        self.state["ai_history"] = history[:80]

    def attach_trade_to_ai_history(self, decision_id: Optional[str], trade: dict):
        if not decision_id:
            return
        history = self.state.setdefault("ai_history", [])
        for entry in history:
            if entry.get("decision_id") != decision_id:
                continue
            linked = entry.setdefault("linked_trades", [])
            linked.insert(
                0,
                {
                    "trade_id": trade.get("id"),
                    "created_at": trade.get("created_at"),
                    "side": trade.get("side"),
                    "outcome": trade.get("outcome"),
                    "price": trade.get("price"),
                    "status": trade.get("status"),
                    "market": trade.get("market"),
                    "realized_profit": trade.get("realized_profit"),
                    "amount_display": trade.get("amount_display"),
                },
            )
            entry["linked_trades"] = linked[:12]
            return

    def get_daily_open(self) -> float:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=1"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        klines = resp.json()
        if not klines:
            raise ValueError("无法获取 BTC 日线数据")
        return float(klines[-1][1])

    def get_recent_klines(self, interval: str, limit: int = 12) -> list:
        url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
        klines = []
        for item in raw:
            klines.append({
                "open_time": item[0],
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            })
        return klines

    def summarize_market_candidates(self, snapshots: list, now_utc: datetime, market_cache: dict) -> list:
        summary = []
        for snapshot in snapshots[:6]:
            end_dt = iso_to_utc_dt(snapshot["endDate"]) if snapshot.get("endDate") else None
            minutes_to_expiry = round(((end_dt - now_utc).total_seconds() / 60), 2) if end_dt else None
            micro = self.get_cached_microstructure(snapshot, market_cache)
            labels = micro.get("labels") or []
            item = {
                "slug": snapshot.get("resolved_slug"),
                "question": snapshot.get("question"),
                "accepting_orders": bool(snapshot.get("acceptingOrders")),
                "minutes_to_expiry": minutes_to_expiry,
            }
            for label in labels[:2]:
                quote = micro.get("outcomes", {}).get(label, {})
                item[label] = {
                    "best_bid": quote.get("best_bid"),
                    "best_ask": quote.get("best_ask"),
                    "spread": quote.get("spread"),
                    "bid_size": quote.get("bid_size"),
                    "ask_size": quote.get("ask_size"),
                }
            summary.append(item)
        return summary

    def get_ai_signal(self, snapshots: list, now_utc: datetime, market_cache: dict) -> dict:
        cached_signal = self.last_ai_signal or self.state.get("last_signal") or {}
        cached_at = cached_signal.get("generated_at")
        if cached_at:
            try:
                age_seconds = (now_utc - iso_to_utc_dt(cached_at)).total_seconds()
                if age_seconds < AI_DECISION_INTERVAL_SECONDS:
                    return cached_signal
            except Exception:
                pass

        btc_data = BTCDataprovider.get_price_with_change()
        if not btc_data:
            raise ValueError("无法获取 BTC 实时价格")

        daily_open = self.get_daily_open()
        current_price = float(btc_data["price"])
        change_percent = ((current_price - daily_open) / daily_open * 100) if daily_open else 0.0
        recent_3m = self.get_recent_klines("3m", 8)
        recent_15m = self.get_recent_klines("15m", 8)
        recent_1h = self.get_recent_klines("1h", 6)
        positions = [{
            "market": p.get("market"),
            "outcome": p.get("outcome"),
            "entry_price": p.get("entry_price"),
            "bid_price": p.get("bid_price"),
            "mark_price": p.get("mark_price"),
            "unrealized_profit": p.get("unrealized_profit"),
            "minutes_to_expiry": round(((iso_to_utc_dt(p["end_date"]) - now_utc).total_seconds() / 60), 2) if p.get("end_date") else None,
        } for p in self.state.get("positions", [])[:4]]

        payload = {
            "timestamp_utc": now_utc.isoformat(),
            "strategy_constraints": {
                "market_interval_minutes": PAPER_MARKET_INTERVAL_MINUTES,
                "bet_amount": PAPER_BET_AMOUNT,
                "min_entry_price": PAPER_MIN_ENTRY_PRICE,
                "max_entry_price": PAPER_MAX_ENTRY_PRICE,
                "max_spread": PAPER_MAX_SPREAD,
                "min_top_book_size": PAPER_MIN_TOP_BOOK_SIZE,
                "min_minutes_to_expiry": PAPER_MIN_MINUTES_TO_EXPIRY,
                "take_profit_usd": PAPER_TAKE_PROFIT_USD,
                "max_open_positions": PAPER_MAX_OPEN_POSITIONS,
            },
            "btc": btc_data,
            "daily_open": round(daily_open, 2),
            "daily_change_percent": round(change_percent, 4),
            "recent_3m_klines": recent_3m,
            "recent_15m_klines": recent_15m,
            "recent_1h_klines": recent_1h,
            "open_positions": positions,
            "candidate_markets": self.summarize_market_candidates(snapshots, now_utc, market_cache),
        }

        ai_result = self.ai_engine.call_model(payload)
        prediction = ai_result.get("prediction", "HOLD")
        if prediction not in {"UP", "DOWN", "HOLD"}:
            prediction = "HOLD"
        action = ai_result.get("action", "HOLD")
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        reason = ai_result.get("reasoning") or "AI 未提供理由"
        factor_lines = [f"- {item}" for item in ai_result.get("key_factors", []) if item]
        risk_lines = [f"- {item}" for item in ai_result.get("risk_flags", []) if item]
        thought_markdown = "\n".join([
            f"模型: {AI_MODEL}",
            f"动作: {action} / 方向: {prediction} / 置信度: {float(ai_result.get('confidence', 0.0)):.2f}",
            f"核心判断: {reason}",
            "",
            "关键依据:",
            *(factor_lines or ["- 无"]),
            "",
            "风险提示:",
            *(risk_lines or ["- 无"]),
        ])

        signal = {
            "decision_id": self.build_decision_id(now_utc),
            "generated_at": now_utc.isoformat(),
            "prediction": prediction,
            "action": action,
            "daily_open": round(daily_open, 2),
            "current_price": round(current_price, 2),
            "change_percent": round(change_percent, 4),
            "reason": reason,
            "btc_data": btc_data,
            "ai_confidence": round(float(ai_result.get("confidence", 0.0)), 4),
            "ai_key_factors": ai_result.get("key_factors", []),
            "ai_risk_flags": ai_result.get("risk_flags", []),
            "ai_thought_markdown": thought_markdown,
            "ai_model": AI_MODEL,
            "ai_source": ai_result.get("source", "llm"),
            "ai_candidate_markets": self.build_ai_candidate_digest(payload.get("candidate_markets", [])),
            "close_positions": bool(ai_result.get("close_positions", False)),
            "decision_interval_seconds": AI_DECISION_INTERVAL_SECONDS,
        }
        self.last_ai_signal = signal
        return signal

    def build_today_slot_slugs(self, now_utc: datetime) -> list:
        now_ny = now_utc.astimezone(NY_TZ)
        today = now_ny.date()
        slots = []
        current_minute = (now_ny.minute // PAPER_MARKET_INTERVAL_MINUTES) * PAPER_MARKET_INTERVAL_MINUTES
        current_slot_ny = datetime(
            today.year,
            today.month,
            today.day,
            now_ny.hour,
            current_minute,
            tzinfo=NY_TZ,
        )

        for offset in range(0, PAPER_FORWARD_SLOT_COUNT + 1):
            start_ny = current_slot_ny + timedelta(minutes=PAPER_MARKET_INTERVAL_MINUTES * offset)
            if start_ny.date() != today:
                continue
            end_ny = start_ny + timedelta(minutes=PAPER_MARKET_INTERVAL_MINUTES)
            start_ts = calendar.timegm(start_ny.astimezone(timezone.utc).utctimetuple())
            slots.append(
                {
                    "slug": f"btc-updown-15m-{start_ts}",
                    "start_ny": start_ny,
                    "end_ny": end_ny,
                }
            )

        return slots

    def fetch_market_snapshot(self, slug: str) -> Optional[dict]:
        try:
            resp = requests.get(f"{self.GAMMA_BASE}/markets/slug/{slug}", timeout=15)
            if resp.status_code != 200:
                return None
            data = resp.json()
            data["resolved_slug"] = slug
            return data
        except Exception:
            return None

    def get_today_market_snapshots(self, now_utc: datetime) -> list:
        snapshots = []
        for slot in self.build_today_slot_slugs(now_utc):
            snapshot = self.fetch_market_snapshot(slot["slug"])
            if not snapshot:
                continue
            snapshot["slot_start_ny"] = slot["start_ny"].isoformat()
            snapshot["slot_end_ny"] = slot["end_ny"].isoformat()
            snapshots.append(snapshot)

        snapshots.sort(key=lambda item: item.get("endDate") or "")
        return snapshots

    def get_price_map(self, snapshot: dict) -> dict:
        outcomes = [str(item).upper() for item in parse_json_list(snapshot.get("outcomes"))]
        prices = [safe_float(item, 0.5) for item in parse_json_list(snapshot.get("outcomePrices"))]
        return {
            outcome: round(price, 4)
            for outcome, price in zip(outcomes, prices)
            if price is not None
        }

    def normalize_book_levels(self, levels, descending: bool) -> list:
        normalized = []
        for level in levels or []:
            price = safe_float((level or {}).get("price"))
            size = safe_float((level or {}).get("size"), 0.0)
            if price is None:
                continue
            normalized.append(
                {
                    "price": round(price, 4),
                    "size": round(size or 0.0, 4),
                }
            )
        return sorted(normalized, key=lambda item: item["price"], reverse=descending)

    def fetch_token_book(self, token_id: str) -> dict:
        if not token_id:
            return {}
        try:
            resp = requests.get(f"{self.CLOB_BASE}/book?token_id={token_id}", timeout=15)
            if resp.status_code != 200:
                return {}
            data = resp.json()
        except Exception:
            return {}

        bids = self.normalize_book_levels(data.get("bids"), descending=True)
        asks = self.normalize_book_levels(data.get("asks"), descending=False)
        best_bid = bids[0]["price"] if bids else None
        best_ask = asks[0]["price"] if asks else None
        spread = round(best_ask - best_bid, 4) if best_bid is not None and best_ask is not None else None
        return {
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_size": bids[0]["size"] if bids else None,
            "ask_size": asks[0]["size"] if asks else None,
            "spread": spread,
        }

    def build_market_microstructure(self, snapshot: Optional[dict], include_books: bool = False) -> dict:
        if not snapshot:
            return {"outcomes": {}, "labels": []}

        outcomes = [str(item).upper() for item in parse_json_list(snapshot.get("outcomes"))]
        if not outcomes:
            outcomes = ["UP", "DOWN"]
        if len(outcomes) < 2:
            outcomes = outcomes + ["DOWN"]

        token_ids = parse_json_list(snapshot.get("clobTokenIds"))
        price_map = self.get_price_map(snapshot)
        snapshot_liquidity = safe_float(snapshot.get("liquidity"), 0.0) or 0.0
        up_bid = safe_float(snapshot.get("bestBid"))
        up_ask = safe_float(snapshot.get("bestAsk"))
        fallback_quotes = {}
        if outcomes:
            first = outcomes[0]
            fallback_quotes[first] = {
                "best_bid": round(up_bid, 4) if up_bid is not None else None,
                "best_ask": round(up_ask, 4) if up_ask is not None else None,
            }
        if len(outcomes) > 1:
            second = outcomes[1]
            fallback_quotes[second] = {
                "best_bid": round(max(0.0, min(1.0, 1 - up_ask)), 4) if up_ask is not None else None,
                "best_ask": round(max(0.0, min(1.0, 1 - up_bid)), 4) if up_bid is not None else None,
            }

        outcome_books = {}
        for idx, outcome in enumerate(outcomes[:2]):
            raw_book = self.fetch_token_book(token_ids[idx]) if include_books and idx < len(token_ids) else {}
            fallback = fallback_quotes.get(outcome, {})
            best_bid = raw_book.get("best_bid", fallback.get("best_bid"))
            best_ask = raw_book.get("best_ask", fallback.get("best_ask"))
            bid_size = raw_book.get("bid_size", snapshot_liquidity)
            ask_size = raw_book.get("ask_size", snapshot_liquidity)
            spread = raw_book.get("spread")
            if spread is None and best_bid is not None and best_ask is not None:
                spread = round(best_ask - best_bid, 4)

            mark_price = None
            if best_bid is not None and best_ask is not None:
                mark_price = round((best_bid + best_ask) / 2, 4)

            last_trade_price = price_map.get(outcome)
            display_price = mark_price if mark_price is not None else last_trade_price
            if spread is not None and spread > 0.10 and last_trade_price is not None:
                display_price = last_trade_price
            if display_price is None:
                display_price = last_trade_price or mark_price or 0.5

            outcome_books[outcome] = {
                "label": outcome,
                "token_id": token_ids[idx] if idx < len(token_ids) else None,
                "best_bid": round(best_bid, 4) if best_bid is not None else None,
                "best_ask": round(best_ask, 4) if best_ask is not None else None,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "spread": round(spread, 4) if spread is not None else None,
                "mark_price": round(mark_price, 4) if mark_price is not None else None,
                "display_price": round(display_price, 4),
                "last_trade_price": round(last_trade_price, 4) if last_trade_price is not None else None,
            }

        return {
            "labels": outcomes[:2],
            "outcomes": outcome_books,
        }

    def get_probabilities(self, snapshot: Optional[dict], reason: str, microstructure: Optional[dict] = None) -> Optional[dict]:
        if not snapshot:
            return None
        microstructure = microstructure or self.build_market_microstructure(snapshot)
        labels = microstructure.get("labels") or [str(item).upper() for item in parse_json_list(snapshot.get("outcomes"))]
        if not labels:
            labels = ["UP", "DOWN"]
        if len(labels) < 2:
            labels = labels + ["DOWN"]
        first = microstructure.get("outcomes", {}).get(labels[0], {})
        second = microstructure.get("outcomes", {}).get(labels[1], {})
        return {
            "yes_price": round(first.get("display_price", 0.5), 4),
            "no_price": round(second.get("display_price", 0.5), 4),
            "outcomes": labels[:2],
            "reason": reason,
        }

    def pick_target_outcome(self, snapshot: dict, prediction: str) -> Optional[str]:
        outcomes = [str(item).upper() for item in parse_json_list(snapshot.get("outcomes"))]
        if not outcomes:
            return None

        preferred_tokens = ("UP", "YES") if prediction == "UP" else ("DOWN", "NO")
        for outcome in outcomes:
            if any(token in outcome for token in preferred_tokens):
                return outcome
        return outcomes[0] if prediction == "UP" else outcomes[min(1, len(outcomes) - 1)]

    def build_market_view(self, snapshot: Optional[dict], microstructure: Optional[dict] = None) -> dict:
        if not snapshot:
            return {}
        microstructure = microstructure or self.build_market_microstructure(snapshot)
        labels = microstructure.get("labels") or []
        target = microstructure.get("outcomes", {}).get(labels[0], {}) if labels else {}
        return {
            "slug": snapshot.get("resolved_slug") or snapshot.get("slug"),
            "question": snapshot.get("question"),
            "end_date": snapshot.get("endDate"),
            "closed": snapshot.get("closed"),
            "accepting_orders": snapshot.get("acceptingOrders"),
            "best_bid": target.get("best_bid"),
            "best_ask": target.get("best_ask"),
            "spread": target.get("spread"),
        }

    def build_order_view(self, position: dict) -> dict:
        return {
            "side": "BUY",
            "outcome": position["outcome"],
            "price": round(position["entry_price"], 4),
            "size": f"{position['shares']:.4f}",
            "tp": position.get("take_profit_price"),
            "sl": None,
            "status": position.get("status", "OPEN"),
            "mark_price": position.get("mark_price"),
            "bid_price": position.get("bid_price"),
            "ask_price": position.get("ask_price"),
            "spread": position.get("spread"),
        }

    def get_cached_microstructure(self, snapshot: Optional[dict], cache: dict) -> dict:
        if not snapshot:
            return {"outcomes": {}, "labels": []}
        slug = snapshot.get("resolved_slug") or snapshot.get("slug") or str(id(snapshot))
        if slug not in cache:
            cache[slug] = self.build_market_microstructure(snapshot)
        return cache[slug]

    def sync_summary(self, reason: str, signal: Optional[dict], focus_market: Optional[dict]):
        positions = sorted(self.state["positions"], key=lambda item: item.get("end_date") or "")
        self.state["positions"] = positions
        self.state["orders"] = [self.build_order_view(position) for position in positions]
        self.state["trades"] = self.state["trades"][:100]
        self.state["closed_markets"] = self.state["closed_markets"][-80:]
        self.state["ai_history"] = self.state.get("ai_history", [])[:80]

        reserved_balance = round(sum(position.get("current_value", 0.0) for position in positions), 4)
        unrealized_pnl = round(sum(position.get("unrealized_profit", 0.0) for position in positions), 4)
        cash_balance = round(safe_float(self.state.get("cash_balance"), PAPER_START_BALANCE) or 0.0, 4)
        ending_balance = round(cash_balance + reserved_balance, 4)
        realized_pnl = round(self.state["stats"].get("total_profit", 0.0), 4)
        total_pnl = round(realized_pnl + unrealized_pnl, 4)
        trade_count = int(self.state["stats"].get("total_trades", 0))
        win_count = int(self.state["stats"].get("winning_trades", 0))
        win_rate = round((win_count / trade_count), 4) if trade_count else 0.0

        self.state["summary"] = {
            "starting_balance": round(PAPER_START_BALANCE, 4),
            "session_started_at": self.state.get("session_started_at"),
            "cash_balance": cash_balance,
            "reserved_balance": reserved_balance,
            "ending_balance": ending_balance,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "open_positions": len(positions),
        }

        self.state["report"] = {
            "mode": "paper_live",
            "session_started_at": self.state.get("session_started_at"),
            "wallet": self.wallet_label,
            "market_slug": (focus_market or {}).get("resolved_slug"),
            "market_question": (focus_market or {}).get("question"),
            "strategy": "LLM 决策 + 当日BTC 15分钟盘口 + Order Book优化纸上交易",
            "reason": reason,
            "profit": total_pnl,
            "roi_percent": round((total_pnl / PAPER_START_BALANCE) * 100, 2) if PAPER_START_BALANCE else 0.0,
            "result": "RUNNING" if positions else "IDLE",
            "ending_balance": ending_balance,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "trade_count": trade_count,
            "min_entry_price": PAPER_MIN_ENTRY_PRICE,
            "max_entry_price": PAPER_MAX_ENTRY_PRICE,
            "take_profit_usd": PAPER_TAKE_PROFIT_USD,
            "max_spread": PAPER_MAX_SPREAD,
            "min_top_book_size": PAPER_MIN_TOP_BOOK_SIZE,
            "min_minutes_to_expiry": PAPER_MIN_MINUTES_TO_EXPIRY,
            "prediction": (signal or {}).get("prediction"),
            "daily_open": (signal or {}).get("daily_open"),
            "daily_change_percent": (signal or {}).get("change_percent"),
        }

        self.state["last_signal"] = signal or self.state.get("last_signal", {})
        self.state["wallet"] = self.wallet_label
        if focus_market:
            self.state["market"] = self.build_market_view(focus_market)
        self.state["generated_at"] = datetime.now(timezone.utc).isoformat()

    def write_live_report(self):
        summary = self.state["summary"]
        report = self.state["report"]
        signal = self.state.get("last_signal", {})
        positions = self.state["positions"]
        recent_trades = self.state["trades"][:10]

        lines = [
            "# Polymarket 15分钟 BTC 纸上交易报告",
            "",
            f"- 更新时间: {datetime.now(timezone.utc).isoformat()}",
            f"- 模式: {report.get('mode', 'paper_live')}",
            f"- 账户: {self.wallet_label}",
            f"- 策略: {report.get('strategy')}",
            f"- AI模型: {signal.get('ai_model', AI_MODEL)}",
            f"- AI预测: {signal.get('prediction', '--')} / 动作 {signal.get('action', '--')} / 置信度 {float(signal.get('ai_confidence', 0.0)):.2f}",
            f"- 日线参考: 开盘 {signal.get('daily_open', '--')} / 现价 {signal.get('current_price', '--')} / 变动 {signal.get('change_percent', '--')}%",
            f"- 入场条件: 目标方向 ask 介于 {PAPER_MIN_ENTRY_PRICE:.2f}-{PAPER_MAX_ENTRY_PRICE:.2f} / 点差 <= {PAPER_MAX_SPREAD:.2f} / 顶档卖盘 >= {PAPER_MIN_TOP_BOOK_SIZE:.0f} shares / 至少剩余 {PAPER_MIN_MINUTES_TO_EXPIRY} 分钟",
            f"- 提前止盈: best bid 浮盈 > ${PAPER_TAKE_PROFIT_USD:.2f}",
            f"- AI 核心判断: {signal.get('reason', '--')}",
            f"- 当前权益: ${summary.get('ending_balance', 0.0):.4f}",
            f"- 可用现金: ${summary.get('cash_balance', 0.0):.4f}",
            f"- 已实现 / 未实现: {summary.get('realized_pnl', 0.0):+.4f} / {summary.get('unrealized_pnl', 0.0):+.4f} USDC",
            f"- 已完成交易: {summary.get('trade_count', 0)}",
            f"- 当前持仓数: {summary.get('open_positions', 0)}",
            "",
            "## 当前持仓",
            "",
        ]

        if positions:
            for position in positions:
                lines.append(
                    "- "
                    f"{position['market']} · {position['outcome']} @ ask {position['entry_price']:.4f} "
                    f"· bid {position.get('bid_price', '--')} / mark {position.get('mark_price', '--')} "
                    f"· 浮盈 {position['unrealized_profit']:+.4f} USDC "
                    f"· 到期 {position['end_date']}"
                )
        else:
            lines.append("- 当前没有未平仓模拟仓位")

        lines.extend(["", "## 最近记录", ""])
        if recent_trades:
            for trade in recent_trades:
                lines.append(
                    "- "
                    f"{trade.get('created_at')} · {trade.get('side')} {trade.get('outcome')} "
                    f"@ {trade.get('price')} · {trade.get('status')} · {trade.get('note', '')}"
                )
        else:
            lines.append("- 暂无模拟成交")

        with open(REPORT_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")

    def update_status_file(self, signal: dict, focus_market: Optional[dict], decision: str, reason: str, error: Optional[str] = None, trading_enabled: Optional[bool] = None):
        focus_microstructure = self.build_market_microstructure(focus_market)
        probabilities = self.get_probabilities(focus_market, reason, microstructure=focus_microstructure)
        report = self.state["report"]
        summary = self.state["summary"]
        if trading_enabled is None:
            trading_enabled = load_trading_control().get("trading_enabled", True)

        write_status(
            market_info=self.build_market_view(focus_market, microstructure=focus_microstructure),
            btc_data=signal.get("btc_data") if signal else None,
            prediction=signal.get("prediction") if signal else "HOLD",
            probabilities=probabilities,
            decision=decision,
            error=error,
            extra={
                "market_slug": (focus_market or {}).get("resolved_slug"),
                "trading_mode": "paper_live",
                "total_trades": self.state["stats"].get("total_trades", 0),
                "paper_profit": report.get("profit"),
                "paper_roi_percent": report.get("roi_percent"),
                "paper_result": report.get("result"),
                "decision_reason": reason,
                "daily_open": signal.get("daily_open") if signal else None,
                "daily_change_percent": signal.get("change_percent") if signal else None,
                "signal_price": signal.get("current_price") if signal else None,
                "signal_reason": signal.get("reason") if signal else None,
                "open_positions": summary.get("open_positions"),
                "cash_balance": summary.get("cash_balance"),
                "reserved_balance": summary.get("reserved_balance"),
                "strategy_name": "LLM 决策 + 当日BTC 15分钟盘口 + Order Book筛选",
                "ai_action": signal.get("action") if signal else None,
                "ai_confidence": signal.get("ai_confidence") if signal else None,
                "ai_model": signal.get("ai_model") if signal else AI_MODEL,
                "ai_source": signal.get("ai_source") if signal else None,
                "ai_decision_id": signal.get("decision_id") if signal else None,
                "ai_thought_markdown": signal.get("ai_thought_markdown") if signal else None,
                "ai_key_factors": signal.get("ai_key_factors") if signal else [],
                "ai_risk_flags": signal.get("ai_risk_flags") if signal else [],
                "ai_decision_interval_seconds": signal.get("decision_interval_seconds") if signal else AI_DECISION_INTERVAL_SECONDS,
                "take_profit_usd": PAPER_TAKE_PROFIT_USD,
                "min_entry_price": PAPER_MIN_ENTRY_PRICE,
                "max_entry_price": PAPER_MAX_ENTRY_PRICE,
                "max_spread": PAPER_MAX_SPREAD,
                "min_top_book_size": PAPER_MIN_TOP_BOOK_SIZE,
                "min_minutes_to_expiry": PAPER_MIN_MINUTES_TO_EXPIRY,
                "trading_enabled": trading_enabled,
            },
        )

    def persist(self, reason: str, signal: Optional[dict], focus_market: Optional[dict], decision: str, error: Optional[str] = None, trading_enabled: Optional[bool] = None):
        self.upsert_ai_history_entry(signal, decision, reason, focus_market=focus_market)
        self.sync_summary(reason, signal, focus_market)
        save_json_file(PAPER_STATE_FILE, self.state)
        self.write_live_report()
        self.update_status_file(signal or {}, focus_market, decision, reason, error=error, trading_enabled=trading_enabled)

    def open_position(self, snapshot: dict, signal: dict, stake: float, entry_price: float, outcome: str, quote: dict, now_utc: datetime) -> str:
        shares = round(stake / entry_price, 6)
        take_profit_price = round((stake + PAPER_TAKE_PROFIT_USD) / shares, 4) if shares else None
        market_slug = snapshot.get("resolved_slug")
        question = snapshot.get("question", market_slug)
        mark_price = safe_float(quote.get("mark_price"), entry_price) or entry_price
        bid_price = safe_float(quote.get("best_bid"), mark_price) or mark_price
        ask_price = safe_float(quote.get("best_ask"), entry_price) or entry_price
        current_value = round(shares * mark_price, 4)
        liquidation_value = round(shares * bid_price, 4)
        unrealized_profit = round(liquidation_value - stake, 4)

        position = {
            "id": f"{market_slug}-{int(now_utc.timestamp())}",
            "market_slug": market_slug,
            "market": question,
            "question": question,
            "outcome": outcome,
            "side": "BUY",
            "stake": round(stake, 4),
            "shares": shares,
            "entry_price": round(entry_price, 4),
            "entry_ask": round(ask_price, 4),
            "current_price": round(mark_price, 4),
            "mark_price": round(mark_price, 4),
            "bid_price": round(bid_price, 4),
            "ask_price": round(ask_price, 4),
            "spread": round(safe_float(quote.get("spread"), 0.0), 4),
            "bid_size": safe_float(quote.get("bid_size"), 0.0),
            "ask_size": safe_float(quote.get("ask_size"), 0.0),
            "current_value": current_value,
            "liquidation_value": liquidation_value,
            "unrealized_profit": unrealized_profit,
            "opened_at": now_utc.isoformat(),
            "created_at": now_utc.isoformat(),
            "end_date": snapshot.get("endDate"),
            "take_profit_usd": PAPER_TAKE_PROFIT_USD,
            "take_profit_price": take_profit_price if take_profit_price and take_profit_price <= 1.0 else None,
            "status": "OPEN",
            "prediction": signal["prediction"],
            "entry_reason": signal["reason"],
            "ai_decision_id": signal.get("decision_id"),
            "ai_confidence": signal.get("ai_confidence"),
            "ai_reasoning": signal.get("reason"),
        }

        self.state["cash_balance"] = round(self.state["cash_balance"] - stake, 4)
        self.state["positions"].append(position)
        trade = {
            "id": f"{position['id']}-entry",
            "created_at": now_utc.isoformat(),
            "side": "BUY",
            "operation": "OPEN",
            "outcome": outcome,
            "amount": f"${stake:.2f} / {shares:.4f} shares",
            "amount_display": f"${stake:.2f}",
            "size": f"{shares:.4f}",
            "price": round(entry_price, 4),
            "status": "OPENED",
            "market": question,
            "note": (
                f"{signal['reason']}，选择 {outcome}，入场 ask {entry_price:.3f} / "
                f"bid {bid_price:.3f} / spread {safe_float(quote.get('spread'), 0.0):.3f}"
            ),
            "market_slug": market_slug,
            "ai_decision_id": signal.get("decision_id"),
            "ai_action": signal.get("action"),
            "ai_confidence": signal.get("ai_confidence"),
            "ai_reasoning": signal.get("reason"),
        }
        self.state["trades"].insert(0, trade)
        self.attach_trade_to_ai_history(signal.get("decision_id"), trade)

        message = f"买入 {question} · {outcome} @ ask {entry_price:.3f}，投入 ${stake:.2f}"
        print(f"🟢 {message}")
        return message

    def close_position(self, position: dict, exit_price: float, exit_reason: str, now_utc: datetime, signal: Optional[dict] = None) -> str:
        proceeds = round(position["shares"] * exit_price, 4)
        profit = round(proceeds - position["stake"], 4)
        self.state["cash_balance"] = round(self.state["cash_balance"] + proceeds, 4)
        self.state["positions"] = [item for item in self.state["positions"] if item["id"] != position["id"]]
        self.state["closed_markets"].append(position["market_slug"])

        self.state["stats"]["total_trades"] += 1
        self.state["stats"]["total_profit"] = round(self.state["stats"]["total_profit"] + profit, 4)
        if profit >= 0:
            self.state["stats"]["winning_trades"] += 1
        else:
            self.state["stats"]["losing_trades"] += 1

        decision_id = (signal or {}).get("decision_id") or position.get("ai_decision_id")
        trade = {
            "id": f"{position['id']}-exit",
            "created_at": now_utc.isoformat(),
            "side": "SELL",
            "operation": "CLOSE",
            "outcome": position["outcome"],
            "amount": f"${proceeds:.2f}",
            "amount_display": f"${proceeds:.2f}",
            "size": f"{position['shares']:.4f}",
            "price": round(exit_price, 4),
            "status": exit_reason,
            "market": position["market"],
            "note": f"{exit_reason}，实现盈亏 {profit:+.4f} USDC",
            "market_slug": position["market_slug"],
            "realized_profit": profit,
            "ai_decision_id": decision_id,
            "ai_action": (signal or {}).get("action"),
            "ai_confidence": (signal or {}).get("ai_confidence"),
            "ai_reasoning": (signal or {}).get("reason") or position.get("ai_reasoning"),
        }
        self.state["trades"].insert(0, trade)
        self.attach_trade_to_ai_history(decision_id, trade)

        result = f"卖出 {position['market']} · {position['outcome']} @ {exit_price:.3f}，盈亏 {profit:+.4f} USDC"
        print(f"🔴 {result}")
        return result

    def refresh_open_positions(self, snapshots_by_slug: dict, now_utc: datetime, market_cache: dict, signal: Optional[dict] = None) -> list:
        messages = []
        updated_positions = []

        for position in list(self.state["positions"]):
            snapshot = snapshots_by_slug.get(position["market_slug"]) or self.fetch_market_snapshot(position["market_slug"])
            if not snapshot:
                updated_positions.append(position)
                continue

            microstructure = self.get_cached_microstructure(snapshot, market_cache)
            quote = microstructure.get("outcomes", {}).get(position["outcome"], {})
            mark_price = safe_float(quote.get("mark_price"))
            if mark_price is None:
                mark_price = safe_float(position.get("mark_price"), position["entry_price"]) or position["entry_price"]
            bid_price = safe_float(quote.get("best_bid"))
            if bid_price is None:
                bid_price = safe_float(position.get("bid_price"), mark_price) or mark_price
            ask_price = safe_float(quote.get("best_ask"))
            if ask_price is None:
                ask_price = safe_float(position.get("ask_price"), mark_price) or mark_price
            current_value = round(position["shares"] * mark_price, 4)
            liquidation_value = round(position["shares"] * bid_price, 4)
            unrealized_profit = round(liquidation_value - position["stake"], 4)
            spread = safe_float(quote.get("spread"))
            if spread is None:
                spread = safe_float(position.get("spread"), 0.0) or 0.0
            bid_size = safe_float(quote.get("bid_size"))
            if bid_size is None:
                bid_size = safe_float(position.get("bid_size"), 0.0) or 0.0
            ask_size = safe_float(quote.get("ask_size"))
            if ask_size is None:
                ask_size = safe_float(position.get("ask_size"), 0.0) or 0.0

            position["current_price"] = round(mark_price, 4)
            position["mark_price"] = round(mark_price, 4)
            position["bid_price"] = round(bid_price, 4)
            position["ask_price"] = round(ask_price, 4)
            position["spread"] = round(spread, 4)
            position["bid_size"] = bid_size
            position["ask_size"] = ask_size
            position["current_value"] = current_value
            position["liquidation_value"] = liquidation_value
            position["unrealized_profit"] = unrealized_profit
            position["status"] = "OPEN"

            should_close = False
            close_reason = ""
            exit_price = bid_price
            end_dt = iso_to_utc_dt(position["end_date"]) if position.get("end_date") else None
            settlement_price = self.get_price_map(snapshot).get(position["outcome"])

            if signal and signal.get("action") == "SELL" and signal.get("close_positions"):
                should_close = True
                close_reason = "AI_EXIT"
                exit_price = bid_price
            elif unrealized_profit > PAPER_TAKE_PROFIT_USD:
                should_close = True
                close_reason = "TAKE_PROFIT_USD"
                exit_price = bid_price
            elif snapshot.get("closed") or (end_dt and now_utc >= end_dt):
                should_close = True
                close_reason = "TIME_EXIT"
                if settlement_price in (0.0, 1.0):
                    exit_price = settlement_price
                else:
                    exit_price = bid_price

            if should_close:
                exit_price = safe_float(exit_price)
                if exit_price is None:
                    exit_price = bid_price
                if exit_price is None:
                    exit_price = mark_price
                if exit_price is None:
                    exit_price = position["entry_price"]
                exit_price = round(exit_price, 4)
                messages.append(self.close_position(position, exit_price, close_reason, now_utc, signal=signal))
            else:
                updated_positions.append(position)

        self.state["positions"] = updated_positions
        return messages

    def scan_entry_opportunities(self, snapshots: list, signal: dict, now_utc: datetime, market_cache: dict) -> tuple:
        messages = []
        hold_reason = ""
        if signal.get("action") != "BUY":
            return messages, f"AI 当前建议 {signal.get('action', 'HOLD')}，暂不新开仓"
        if signal["prediction"] == "HOLD":
            return messages, "AI 预测未形成明确方向，继续空仓等待"

        open_slugs = {position["market_slug"] for position in self.state["positions"]}
        closed_slugs = set(self.state["closed_markets"])
        target_outcome_name = "UP/YES" if signal["prediction"] == "UP" else "DOWN/NO"
        candidates = []
        remaining_slots = max(0, PAPER_MAX_OPEN_POSITIONS - len(self.state["positions"]))

        for snapshot in snapshots:
            slug = snapshot.get("resolved_slug")
            if not slug or slug in open_slugs or slug in closed_slugs:
                continue

            if not snapshot.get("acceptingOrders") or snapshot.get("closed"):
                continue

            end_date = snapshot.get("endDate")
            if end_date and now_utc >= iso_to_utc_dt(end_date):
                continue

            if remaining_slots <= 0:
                hold_reason = f"已达到最多 {PAPER_MAX_OPEN_POSITIONS} 个并行模拟持仓"
                break

            if self.state["cash_balance"] < PAPER_BET_AMOUNT:
                hold_reason = f"可用纸上余额不足，当前仅剩 ${self.state['cash_balance']:.2f}"
                break

            end_dt = iso_to_utc_dt(end_date) if end_date else None
            minutes_to_expiry = ((end_dt - now_utc).total_seconds() / 60) if end_dt else 9999
            if minutes_to_expiry < PAPER_MIN_MINUTES_TO_EXPIRY:
                if not hold_reason:
                    hold_reason = (
                        f"{snapshot.get('question')} 距离到期只剩 {max(0, int(minutes_to_expiry))} 分钟，"
                        f"低于最小剩余时间 {PAPER_MIN_MINUTES_TO_EXPIRY} 分钟"
                    )
                continue

            outcome = self.pick_target_outcome(snapshot, signal["prediction"])
            microstructure = self.get_cached_microstructure(snapshot, market_cache)
            quote = microstructure.get("outcomes", {}).get(outcome or "", {})
            entry_price = safe_float(quote.get("best_ask"))
            if entry_price is None:
                continue

            best_bid = safe_float(quote.get("best_bid"))
            spread = safe_float(quote.get("spread"))
            ask_size = safe_float(quote.get("ask_size"), 0.0)
            required_shares = round(PAPER_BET_AMOUNT / entry_price, 4) if entry_price else 0.0
            min_depth_required = max(required_shares, PAPER_MIN_TOP_BOOK_SIZE)

            if entry_price < PAPER_MIN_ENTRY_PRICE:
                if not hold_reason:
                    hold_reason = (
                        f"{snapshot.get('question')} 的 {target_outcome_name} 买一 ask {entry_price:.3f} "
                        f"低于最小入场价 {PAPER_MIN_ENTRY_PRICE:.2f}"
                    )
                continue

            if entry_price > PAPER_MAX_ENTRY_PRICE:
                if not hold_reason:
                    hold_reason = (
                        f"{snapshot.get('question')} 的 {target_outcome_name} 买一 ask {entry_price:.3f} "
                        f"高于入场上限 {PAPER_MAX_ENTRY_PRICE:.2f}"
                    )
                continue

            if spread is not None and spread > PAPER_MAX_SPREAD:
                if not hold_reason:
                    hold_reason = (
                        f"{snapshot.get('question')} 的点差 {spread:.3f} 过宽，"
                        f"超过上限 {PAPER_MAX_SPREAD:.2f}"
                    )
                continue

            if ask_size < min_depth_required:
                if not hold_reason:
                    hold_reason = (
                        f"{snapshot.get('question')} 的卖一深度仅 {ask_size:.2f} shares，"
                        f"低于阈值 {min_depth_required:.2f}"
                    )
                continue

            edge_score = round((PAPER_MAX_ENTRY_PRICE - entry_price) - ((spread or 0.0) * 0.5), 6)
            candidates.append(
                {
                    "snapshot": snapshot,
                    "outcome": outcome,
                    "entry_price": round(entry_price, 4),
                    "quote": quote,
                    "score": edge_score,
                    "minutes_to_expiry": minutes_to_expiry,
                    "best_bid": best_bid,
                    "ask_size": ask_size,
                }
            )

        candidates.sort(
            key=lambda item: (
                -item["score"],
                item["entry_price"],
                safe_float(item["quote"].get("spread"), 999),
                item["minutes_to_expiry"],
            )
        )

        max_new_positions = min(PAPER_MAX_NEW_POSITIONS_PER_CYCLE, remaining_slots)
        for candidate in candidates[:max_new_positions]:
            snapshot = candidate["snapshot"]
            slug = snapshot.get("resolved_slug")
            messages.append(
                self.open_position(
                    snapshot,
                    signal,
                    PAPER_BET_AMOUNT,
                    candidate["entry_price"],
                    candidate["outcome"],
                    candidate["quote"],
                    now_utc,
                )
            )
            if slug:
                open_slugs.add(slug)

        if not messages and not hold_reason:
            hold_reason = "今天的 15 分钟 BTC 盘口暂时没有满足价格区间 / 点差 / 深度 条件的机会"
        elif len(candidates) > max_new_positions and messages:
            hold_reason = f"本轮仅执行最优的 {max_new_positions} 个盘口，其余候选继续等待更优价格"
        return messages, hold_reason

    def pick_focus_market(self, snapshots: list) -> Optional[dict]:
        positions = sorted(self.state["positions"], key=lambda item: item.get("end_date") or "")
        snapshot_map = {snapshot.get("resolved_slug"): snapshot for snapshot in snapshots}

        for position in positions:
            if position["market_slug"] in snapshot_map:
                return snapshot_map[position["market_slug"]]

        for snapshot in snapshots:
            if snapshot.get("acceptingOrders") and not snapshot.get("closed"):
                return snapshot

        return snapshots[0] if snapshots else None

    async def run_cycle(self):
        now_utc = datetime.now(timezone.utc)
        trading_enabled = load_trading_control().get("trading_enabled", True)
        snapshots = self.get_today_market_snapshots(now_utc)
        if not snapshots:
            raise ValueError("未找到当前窗口内的 BTC 15 分钟盘口")

        snapshots_by_slug = {snapshot.get("resolved_slug"): snapshot for snapshot in snapshots}
        market_cache = {}
        signal = self.get_ai_signal(snapshots, now_utc, market_cache)
        close_messages = self.refresh_open_positions(snapshots_by_slug, now_utc, market_cache, signal=signal)
        if trading_enabled:
            open_messages, hold_reason = self.scan_entry_opportunities(snapshots, signal, now_utc, market_cache)
        else:
            open_messages = []
            hold_reason = (
                "交易已关闭，不再自动新开仓；已有持仓仍按止盈和到期规则处理"
                if self.state["positions"]
                else "交易已关闭，当前不会自动新开仓"
            )
        focus_market = self.pick_focus_market(snapshots)

        if open_messages:
            decision = "BUY"
            reason = "；".join(open_messages[:2])
        elif close_messages:
            decision = "SELL"
            reason = "；".join(close_messages[:2])
        elif not trading_enabled:
            decision = "HOLD"
            reason = hold_reason or "交易已关闭，当前不会自动新开仓"
        elif self.state["positions"]:
            lead_position = sorted(self.state["positions"], key=lambda item: item.get("end_date") or "")[0]
            decision = "HOLD"
            reason = (
                f"持有 {lead_position['market']} · {lead_position['outcome']}，"
                f"当前浮盈 {lead_position['unrealized_profit']:+.4f} USDC"
            )
        else:
            decision = "HOLD"
            reason = hold_reason or signal["reason"]

        self.persist(reason, signal, focus_market, decision, trading_enabled=trading_enabled)

    async def run(self):
        print("\n🤖 Polymarket 15分钟 BTC 纸上交易启动")
        print(f"   初始资金: ${PAPER_START_BALANCE:.2f}")
        print(f"   单盘口仓位: ${PAPER_BET_AMOUNT:.2f}")
        print(f"   买入 ask 区间: {PAPER_MIN_ENTRY_PRICE:.2f} - {PAPER_MAX_ENTRY_PRICE:.2f}")
        print(f"   最大点差: {PAPER_MAX_SPREAD:.2f}")
        print(f"   顶档深度要求: {PAPER_MIN_TOP_BOOK_SIZE:.0f} shares")
        print(f"   最少剩余时间: {PAPER_MIN_MINUTES_TO_EXPIRY} 分钟")
        print(f"   提前止盈: best bid 浮盈 > ${PAPER_TAKE_PROFIT_USD:.2f}")
        print(f"   最大同时持仓: {PAPER_MAX_OPEN_POSITIONS}")
        print(f"   单轮最多新开仓: {PAPER_MAX_NEW_POSITIONS_PER_CYCLE}")
        print(f"   AI 决策模型: {AI_MODEL}")
        print(f"   AI 决策间隔: {AI_DECISION_INTERVAL_SECONDS} 秒")
        print(f"   轮询间隔: {PAPER_POLL_INTERVAL_SECONDS} 秒")

        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                message = f"纸上交易循环异常: {e}"
                print(f"❌ {message}")
                focus_market = self.build_market_view(None)
                self.persist(
                    message,
                    self.state.get("last_signal"),
                    None,
                    "HOLD",
                    error=str(e),
                    trading_enabled=load_trading_control().get("trading_enabled", True),
                )
            await asyncio.sleep(PAPER_POLL_INTERVAL_SECONDS)


# ==================== 主程序 ====================

async def main():
    """主入口"""
    if TRADING_MODE == "paper_replay":
        print(f"🧪 当前模式: {TRADING_MODE}")
        print(f"🎯 目标市场: {BTC_UPDOWN_MARKET_ID}")
        print(f"💰 纸上仓位: ${PAPER_BET_AMOUNT:.2f}")
        print(f"🛡️ 止盈 / 止损: {TAKE_PROFIT_PERCENT:.0%} / {STOP_LOSS_PERCENT:.0%}")
        paper_bot = PaperReplayBot()
        await paper_bot.run()
        return

    if TRADING_MODE.startswith("paper"):
        print(f"🧪 当前模式: {TRADING_MODE}")
        print("📘 使用 LLM 每 3 分钟决策 + 当日 BTC 15m 盘口 纸上交易策略")
        paper_bot = ContinuousPaperTradingBot()
        await paper_bot.run()
        return

    if not POLYMARKET_WALLET_ADDRESS:
        print("❌ 请在 .env 文件中设置 POLYMARKET_WALLET_ADDRESS")
        return

    if not POLYMARKET_API_KEY:
        print("❌ Live 模式需要在 .env 文件中设置 POLYMARKET_API_KEY")
        print("   参考 .env.example")
        return

    bot = TradingBot()
    await bot.run_forever(interval_seconds=300)  # 5 分钟


if __name__ == "__main__":
    asyncio.run(main())
