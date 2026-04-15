import os
import json
from dotenv import dotenv_values, load_dotenv
from zoneinfo import ZoneInfo
from pathlib import Path

# 路径设置
BASE_DIR = Path(__file__).parent.parent.parent.absolute()
_current_dir = BASE_DIR
DATA_DIR = os.path.join(_current_dir, "data")
STATUS_FILE = os.path.join(DATA_DIR, "bot_status.json")
PAPER_STATE_FILE = os.path.join(DATA_DIR, "paper_trade_state.json")
REPORT_FILE = os.path.join(DATA_DIR, "paper_trade_report.md")
CONTROL_FILE = os.path.join(DATA_DIR, "trading_control.json")
ENV_FILE = os.path.join(_current_dir, ".env")

# 加载环境变量
load_dotenv(ENV_FILE, override=True)

class Config:
    @staticmethod
    def get_runtime_config():
        """从 trading_control.json 加载运行时配置（允许 Web 端覆盖）"""
        if os.path.exists(CONTROL_FILE):
            try:
                with open(CONTROL_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {}

    @staticmethod
    def get_env_config():
        """直接从 .env 读取最新值，支持运行中热更新。"""
        try:
            return dotenv_values(ENV_FILE)
        except Exception:
            return {}

    @classmethod
    def get(cls, key, default=None):
        runtime = cls.get_runtime_config()
        # 运行时配置优先级最高
        if key in runtime:
            return runtime[key]
        env_config = cls.get_env_config()
        if key in env_config and env_config[key] not in (None, ""):
            return env_config[key]
        return os.getenv(key, default)

    @classmethod
    def get_bool(cls, key, default="true"):
        val = str(cls.get(key, default)).lower()
        return val in ("true", "1", "yes", "on")

    @classmethod
    def get_float(cls, key, default="0"):
        return float(cls.get(key, default))

    @classmethod
    def get_int(cls, key, default="0"):
        return int(cls.get(key, default))

# -------------------- 常量映射 --------------------

# 环境与地址
NY_TZ = ZoneInfo("America/New_York")
POLYMARKET_WALLET_ADDRESS = Config.get("POLYMARKET_WALLET_ADDRESS", "")
POLYMARKET_FUNDER_ADDRESS = Config.get("POLYMARKET_FUNDER_ADDRESS", POLYMARKET_WALLET_ADDRESS)
POLYMARKET_SIGNATURE_TYPE = Config.get_int("POLYMARKET_SIGNATURE_TYPE", "1")

# API 凭证 (支持动态覆盖)
POLYMARKET_API_KEY = Config.get("POLYMARKET_API_KEY", "")
POLYMARKET_API_SECRET = Config.get("POLYMARKET_API_SECRET", "")
POLYMARKET_API_PASSPHRASE = Config.get("POLYMARKET_API_PASSPHRASE", "")
POLYMARKET_PRIVATE_KEY = Config.get("POLYMARKET_PRIVATE_KEY", "")

# 交易基础配置
BET_AMOUNT = Config.get_float("BET_AMOUNT", "5")
MAX_BET_AMOUNT = Config.get_float("MAX_BET_AMOUNT", "50")
MIN_PROBABILITY_DIFF = Config.get_float("MIN_PROBABILITY_DIFF", "0.1")
STOP_LOSS_ENABLED = Config.get_bool("STOP_LOSS_ENABLED", "true")
STOP_LOSS_PERCENT = Config.get_float("STOP_LOSS_PERCENT", "0.10")
TAKE_PROFIT_PERCENT = Config.get_float("TAKE_PROFIT_PERCENT", "0.18")

# 模式配置
TRADING_MODE = Config.get("TRADING_MODE", "paper").strip().lower()
PAPER_START_BALANCE = Config.get_float("PAPER_START_BALANCE", "100")
PAPER_BET_AMOUNT = Config.get_float("PAPER_BET_AMOUNT", str(BET_AMOUNT))
PAPER_TAKE_PROFIT_USD = Config.get_float("PAPER_TAKE_PROFIT_USD", "0.12")
PAPER_POLL_INTERVAL_SECONDS = Config.get_int("PAPER_POLL_INTERVAL_SECONDS", "15")

# AI 配置
AI_ENABLED = Config.get_bool("AI_ENABLED", "true")
AI_DECISION_INTERVAL_SECONDS = Config.get_int("AI_DECISION_INTERVAL_SECONDS", "180")
AI_BASE_URL = Config.get("AI_BASE_URL", "https://api.openai.com/v1")
AI_API_KEY = Config.get("AI_API_KEY", "")
AI_MODEL = Config.get("AI_MODEL", "gpt-4o-mini")
AI_TEMPERATURE = Config.get_float("AI_TEMPERATURE", "0.7")

# 市场配置
BTC_UPDOWN_MARKET_ID = Config.get("BTC_UPDOWN_MARKET_ID", "")
BTC_PRICE_SOURCE = Config.get("BTC_PRICE_SOURCE", "binance")
MARKET_SELECTION_MODE = Config.get("MARKET_SELECTION_MODE", "manual")
TARGET_MARKET_SLUG = Config.get("TARGET_MARKET_SLUG", "")
TARGET_MARKET_URL = Config.get("TARGET_MARKET_URL", "")
STRATEGY_PROFILE = Config.get("STRATEGY_PROFILE", "generic_binary")
ALLOW_MULTI_OUTCOME = Config.get_bool("ALLOW_MULTI_OUTCOME", "false")

# 实盘额外配置
DRY_RUN = Config.get_bool("DRY_RUN", "true")
LIVE_BET_AMOUNT = Config.get_float("LIVE_BET_AMOUNT", "1")
LIVE_MAX_OPEN_POSITIONS = Config.get_int("LIVE_MAX_OPEN_POSITIONS", "1")
