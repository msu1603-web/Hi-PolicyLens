# llm_client.py
import os, requests, json

def _get_secret(name, default=None):
    try:
        import streamlit as st
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

class LLMClient:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=60):
        self.base_url = (base_url or _get_secret("POTENS_BASE_URL", "https://api.potens.ai")).rstrip("/")
        self.api_key  = api_key  or _get_secret("POTENS_API_KEY")
        self.model    = model    or _get_secret("POTENS_MODEL", "claude-3-5-sonnet-20240620")
        self.timeout  = timeout

    def _fmt(self, r):
        try:
            return {"status": r.status_code, "reason": r.reason, "text": r.text}
        except Exception:
            return {"status": None, "reason": "no-reason", "text": "no-body"}

    def chat_json(self, system, user, temperature=0.2):
        # 1) OpenAI 호환
        url1 = f"{self.base_url}/v1/chat/completions"
        try:
            r = requests.post(
                url1,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    "temperature": temperature
                },
                timeout=self.timeout
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            err1 = self._fmt(r)
        except requests.RequestException as e:
            err1 = {"status": "exception", "reason": str(e)}

        # 2) Anthropic(Claude) 스타일
        url2 = f"{self.base_url}/v1/messages"
        try:
            r = requests.post(
                url2,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "temperature": temperature,
                    "messages": [
                        {"role":"system","content": system},
                        {"role":"user","content": user}
                    ]
                },
                timeout=self.timeout
            )
            if r.status_code == 200:
                data = r.json()
                parts = [blk.get("text","") for blk in data.get("content", []) if blk.get("type")=="text"]
                return "\n".join(parts).strip()
            err2 = self._fmt(r)
        except requests.RequestException as e:
            err2 = {"status": "exception", "reason": str(e)}

        # 실패 상세를 문자열로 반환(raise 대신 문자열) -> 앱에서 그대로 보여줌
        return json.dumps({"_error": {"openai_compatible": err1, "anthropic_style": err2}}, ensure_ascii=False)

    # 연결 진단: 두 엔드포인트를 가볍게 호출하고 원문 반환
    def diagnose(self):
        results = {}
        # /v1/chat/completions
        try:
            r = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": [{"role":"user","content":"ping"}]},
                timeout=self.timeout
            )
            results["openai_compatible"] = self._fmt(r)
        except requests.RequestException as e:
            results["openai_compatible"] = {"status":"exception","reason":str(e)}

        # /v1/messages
        try:
            r = requests.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={"model": self.model, "max_tokens": 16, "messages":[{"role":"user","content":"ping"}]},
                timeout=self.timeout
            )
            results["anthropic_style"] = self._fmt(r)
        except requests.RequestException as e:
            results["anthropic_style"] = {"status":"exception","reason":str(e)}

        return results
