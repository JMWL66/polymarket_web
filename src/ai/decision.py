import aiohttp
import json
import re
import logging
from typing import Optional, Dict, Any
from ..core.config import Config

logger = logging.getLogger("ai_decision")

SYSTEM_PROMPT = """你是一个专注于 Polymarket 二元预测市场的交易决策助手。

你的任务是根据提供的市场问题、到期时间、当前赔率和盘口深度，在二元市场中判断是否值得买入某一边。

请严格按照以下 JSON 格式返回，不要输出任何其他文字：
{
  "action": "BUY" | "SKIP",
  "outcome_index": 0 | 1 | null,
  "outcome_label": "YES/NO 等标签，无法确定时可为 null",
  "confidence": 0.0~1.0,
  "reason": "一句话说明理由（50字以内）"
}

说明：
- BUY: 仅当某一边存在明确优势时才返回，并指定 outcome_index
- SKIP: 信号不明朗、盘口太差、临近到期或信息不足时返回
- confidence: 你的信心度，低于 0.6 时通常应返回 SKIP"""


def _extract_json(text: str) -> Optional[str]:
    """从可能包含 <think>...</think> 的响应中提取 JSON"""
    # 剥离 <think>...</think> 推理块（MiniMax 推理模型特有）
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # 直接尝试整体解析
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # 从文本中找到第一个完整 JSON 对象
    match = re.search(r'\{[^{}]*(?:"action"|\"prediction\")[^{}]*\}', text, re.DOTALL)
    if match:
        return match.group(0)

    return None


class AIDecisionEngine:
    """封装 AI 决策逻辑"""

    def __init__(self):
        self.enabled = Config.get_bool("AI_ENABLED", "true")
        self.base_url = Config.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = Config.get("AI_API_KEY", "")
        self.model = Config.get("AI_MODEL", "gpt-4o-mini")

    async def get_prediction(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用 AI 接口获取预测，返回 {prediction, confidence, reason} 或 None"""
        if not self.enabled or not self.api_key:
            logger.warning("AI 未启用或未配置 API Key")
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": Config.get_float("AI_TEMPERATURE", "0.1"),
            "max_tokens": Config.get_int("AI_MAX_TOKENS", "300"),
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"AI API 返回 {resp.status}: {error_text[:200]}")
                        return None

                    data = await resp.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    logger.debug(f"AI 原始返回: {raw_content[:300]}")

                    json_str = _extract_json(raw_content)
                    if not json_str:
                        logger.error(f"无法从 AI 响应中提取 JSON: {raw_content[:200]}")
                        return None

                    result = json.loads(json_str)

                    action = str(result.get("action", "")).upper()
                    if action not in ("BUY", "SKIP"):
                        prediction = str(result.get("prediction", "SKIP")).upper()
                        if prediction in ("UP", "YES"):
                            action = "BUY"
                            result.setdefault("outcome_index", 0)
                        elif prediction in ("DOWN", "NO"):
                            action = "BUY"
                            result.setdefault("outcome_index", 1)
                        else:
                            action = "SKIP"
                    result["action"] = action

                    outcome_index = result.get("outcome_index")
                    try:
                        result["outcome_index"] = int(outcome_index) if outcome_index is not None else None
                    except Exception:
                        result["outcome_index"] = None

                    outcome_label = result.get("outcome_label")
                    result["outcome_label"] = str(outcome_label).upper() if outcome_label not in (None, "") else None
                    result.setdefault("confidence", 0.5)
                    result.setdefault("reason", "AI 未提供理由")

                    logger.info(
                        "AI 决策: %s outcome=%s | 信心: %.0f%% | %s",
                        result["action"],
                        result.get("outcome_index"),
                        float(result["confidence"]) * 100,
                        result["reason"],
                    )
                    return result

            except Exception as e:
                import traceback
                logger.error(f"AI 调用异常: {type(e).__name__}: {e}\n{traceback.format_exc()}")
                return None
