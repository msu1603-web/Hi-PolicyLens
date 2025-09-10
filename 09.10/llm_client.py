# llm_client.py
import os, requests
import json

def _get_secret(name, default=None):
    try:
        import streamlit as st
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

class LLMClient:
    """
    1차: OpenAI 호환 /v1/chat/completions
    2차: Anthropic(Claude) /v1/messages  자동 재시도
    """
    def __init__(self, base_url=None, api_key=None, model=None, timeout=60):
        self.base_url = (base_url or _get_secret("POTENS_BASE_URL", "https://api.potens.ai")).rstrip("/")
        self.api_key  = api_key  or _get_secret("POTENS_API_KEY")
        self.model    = model    or _get_secret("POTENS_MODEL", "claude-4-sonnet")
        self.timeout  = timeout

    # --- 헬퍼: 실패 시 상세 에러 문자열 만들기
    def _fmt_err(self, r):
        try:
            return f"{r.status_code} {r.reason} | {r.text}"
        except Exception:
            return "HTTP error (no body)"

    def chat_json(self, system, user, temperature=0.2):
        # 1) OpenAI 호환 시도
        try:
            url = f"{self.base_url}/v1/chat/completions"
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
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            # 404/400/401 등 실패면 Anthropic 스타일로 재시도
            err1 = self._fmt_err(r)
        except requests.RequestException as e:
            err1 = f"OpenAI-compatible call failed: {e}"

        # 2) Anthropic(Claude) API 스타일 재시도
        try:
            url = f"{self.base_url}/v1/messages"
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",  # 흔한 기본 버전
                "content-type": "application/json"
            }
            payload = {
                "model": self.model,
                "max_tokens": 1024,
                "temperature": temperature,
                "messages": [
                    {"role":"system","content": system},
                    {"role":"user","content": user}
                ]
            }
            r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if r.status_code == 200:
                # Anthropic 응답 파싱
                data = r.json()
                # text만 이어붙이기
                parts = []
                for blk in data.get("content", []):
                    if blk.get("type") == "text":
                        parts.append(blk.get("text",""))
                return "\n".join(parts).strip()
            err2 = self._fmt_err(r)
        except requests.RequestException as e:
            err2 = f"Anthropic-style call failed: {e}"

        # 둘 다 실패 → 에러를 그대로 올려서 화면에 보이게
        raise requests.HTTPError(f"OpenAI-compatible error: {err1}\nAnthropic-style error: {err2}")
