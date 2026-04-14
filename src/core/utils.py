import json
import os
from datetime import datetime, timezone
from typing import Optional, Any

def load_json_file(path: str, default: Any) -> Any:
    """从文件加载 JSON，失败则返回默认值"""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def save_json_file(path: str, data: Any):
    """保存数据为 JSON 格式"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """安全转换为 float"""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def extract_market_slug(market_input: str) -> str:
    """从市场输入解析出 slug"""
    if not market_input:
        return ""
    if "polymarket.com/event/" in market_input:
        return market_input.split("polymarket.com/event/")[-1].split("#")[0].split("?")[0]
    return market_input

def short_wallet(address: str) -> str:
    """展示缩写的钱包地址"""
    if not address or len(address) < 10:
        return address or "Unknown"
    return f"{address[:6]}...{address[-4:]}"

def iso_to_utc_dt(value: str) -> datetime:
    """ISO 字符串转 UTC datetime"""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

def parse_json_list(value: Any) -> list:
    """解析 JSON 列表字符串"""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except Exception:
        return []

def load_trading_control(control_file_path: str) -> dict:
    """从控制文件加载交易开关状态"""
    state = {"trading_enabled": True}
    try:
        if os.path.exists(control_file_path):
            with open(control_file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            state["trading_enabled"] = bool(raw.get("trading_enabled", True))
            state["updated_at"] = raw.get("updated_at")
    except Exception:
        pass
    return state
