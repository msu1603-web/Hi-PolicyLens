import os, requests

def _get_secret(name, default=None):
    try:
        import streamlit as st
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

class LLMClient:
    """
    Potens가 OpenAI 호환이라고 가정.
    기본 모델은 Claude 4 Sonnet.
    """
    def __init__(self, base_url=None, api_key=None, model=None, timeout=60):
        self.base_url = (base_url or _get_secret("POTENS_BASE_URL", "https://api.potens.ai")).rstrip("/")
        self.api_key  = api_key  or _get_secret("POTENS_API_KEY")
        self.model    = model    or _get_secret("POTENS_MODEL", "claude-4-sonnet")
        self.timeout  = timeout

    def chat_json(self, system, user, temperature=0.2):
        url = f"{self.base_url}/v1/chat/completions"  # OpenAI 호환 엔드포인트
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature
        }
        r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
