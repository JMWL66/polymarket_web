import aiohttp
import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
from ..core.config import Config, AI_ENABLED, AI_BASE_URL, AI_API_KEY, AI_MODEL, AI_TEMPERATURE

logger = logging.getLogger("ai_decision")

class AIDecisionEngine:
    """封装 AI 决策逻辑"""

    def __init__(self):
        self.enabled = Config.get_bool("AI_ENABLED", "true")
        self.base_url = Config.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = Config.get("AI_API_KEY", "")
        self.model = Config.get("AI_MODEL", "gpt-4o-mini")

    async def get_prediction(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用 AI 接口获取预测"""
        if not self.enabled or not self.api_key:
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个资深的加密货币交易员，擅长通过 BTC 价格走势和市场深度进行短线判断。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": Config.get_float("AI_TEMPERATURE", "0.2"),
            "response_format": {"type": "json_object"}
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data['choices'][0]['message']['content']
                        return json.loads(content)
                    else:
                        error_text = await resp.text()
                        logger.error(f"AI API error ({resp.status}): {error_text}")
            except Exception as e:
                logger.error(f"AI prediction exception: {e}")
        return None
