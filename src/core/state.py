import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from .utils import load_json_file, save_json_file
from .config import PAPER_START_BALANCE, PAPER_STATE_FILE, STATUS_FILE

logger = logging.getLogger("state_manager")

class StateManager:
    """管理机器人状态持久化 (PnL, Positions, trades)"""
    
    def __init__(self, state_file: str):
        self.state_file = state_file
        self.state = self.load()

    def load(self) -> Dict[str, Any]:
        return load_json_file(self.state_file, self._get_default_state())

    def save(self):
        save_json_file(self.state_file, self.state)

    def get_state(self) -> Dict[str, Any]:
        return self.state

    def update(self, key: str, value: Any):
        self.state[key] = value
        self.save()

    def _get_default_state(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "mode": "paper_live",
            "generated_at": now,
            "session_started_at": now,
            "cash_balance": PAPER_START_BALANCE,
            "positions": [],
            "orders": [],
            "trades": [],
            "closed_markets": [],
            "ai_history": [],
            "stats": {"total_trades": 0, "winning_trades": 0, "losing_trades": 0, "total_profit": 0.0},
            "market": {},
            "summary": {},
            "report": {},
            "last_signal": {}
        }

class StatusExporter:
    """负责将当前活跃状态写入 bot_status.json 供前端读取"""
    
    @staticmethod
    def export(data: Dict[str, Any]):
        save_json_file(STATUS_FILE, data)
