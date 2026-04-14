import os
import requests
import json
from dotenv import load_dotenv

# 加载 .env
_current_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(os.path.dirname(_current_dir), ".env")
load_dotenv(_env_path, override=True)

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = "MiniMax-M2.7-highspeed" # 指定正确的前缀

def test_minimax():
    url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # 模拟 bot.py 的原始 payload
    body = {
        "model": AI_MODEL,
        "temperature": 0.2,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Please return response in JSON format."},
            {"role": "user", "content": "Hello, how are you? Return a JSON like {'status': 'ok'}"},
        ],
    }
    
    print(f"Testing URL: {url}")
    print(f"Using Model: {AI_MODEL}")
    
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=20)
        print(f"Status Code: {resp.status_code}")
        print(f"Response Body: {resp.text}")
        
        if resp.status_code == 400:
            print("\n--- Detected 400, trying without response_format ---")
            del body["response_format"]
            resp2 = requests.post(url, headers=headers, json=body, timeout=20)
            print(f"Retry Status Code: {resp2.status_code}")
            print(f"Retry Response Body: {resp2.text}")
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_minimax()
