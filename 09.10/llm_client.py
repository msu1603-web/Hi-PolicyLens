# llm_client.py  — Potens 전용(비-호환) 엔드포인트 버전
import os, requests, json

def _get_secret(name, default=None):
    try:
        import streamlit as st
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

class LLMClient:
    """
    Potens 전용 API:
      POST {BASE_URL}/api/chat
      Headers: Authorization: Bearer <API_KEY>, Content-Type: application/json
      Body:    { "prompt": "<system + user 합친 프롬프트>", "temperature": 0.2 }  # 필요한 필드만 사용
    응답은 서비스마다 키가 다를 수 있어 여러 키를 순차적으로 탐색함.
    """
    def __init__(self, base_url=None, api_key=None, model=None, timeout=60):
        # model은 현재 포텐스 샘플에는 필요 없어 보이나, 호환성 위해 남겨둔다.
        self.base_url = (base_url or _get_secret("POTENS_BASE_URL", "https://ai.potens.ai")).rstrip("/")
        self.api_key  = api_key  or _get_secret("POTENS_API_KEY")
        self.model    = model    or _get_secret("POTENS_MODEL", "")  # 미사용 가능
        self.timeout  = timeout

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _parse_response_text(self, r):
        """
        포텐스 응답 포맷이 명확히 문서화되지 않았으므로, 가능한 키 후보를 순차 탐색.
        """
        # JSON 시도
        try:
            data = r.json()
            # 가장 흔한 후보 키들
            for key in ["answer", "output", "response", "text", "message", "result"]:
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            # 중첩 구조 후보
            if "data" in data:
                d = data["data"]
                for key in ["answer", "output", "response", "text", "message", "result"]:
                    if isinstance(d, dict) and isinstance(d.get(key), str):
                        v = d.get(key)
                        if v.strip(): return v
            # 최후의 수단: JSON 전체를 문자열로
            return json.dumps(data, ensure_ascii=False)
        except ValueError:
            # JSON 아니면 그냥 텍스트
            return r.text

    def chat_json(self, system, user, temperature=0.2):
        """
        우리 앱은 JSON 응답을 기대하므로, 이 함수는
        - Potens에서 텍스트를 받아
        - 그대로 문자열 반환(모델이 JSON 형식으로 출력하도록 프롬프트에서 강제)
        를 수행한다.
        """
        url = f"{self.base_url}/api/chat"
        # Potens는 "prompt" 한 필드만 받는 것으로 가정.
        # system + user를 합쳐 전송 (모델에게 JSON으로 답하라고 지시)
        combined_prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{user}"
        payload = {
            "prompt": combined_prompt,
            "temperature": temperature
        }
        # model 파라미터가 필요하다면 여기에 추가:
        if self.model:
            payload["model"] = self.model

        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
            if r.status_code == 200:
                return self._parse_response_text(r)
            # 실패면 상세 에러를 문자열로 반환하여 화면에 표시
            err = {
                "status": r.status_code,
                "reason": r.reason,
                "text": r.text
            }
            return json.dumps({"_error": {"potens_api_chat": err}}, ensure_ascii=False)
        except requests.RequestException as e:
            return json.dumps({"_error": {"potens_api_chat": str(e)}}, ensure_ascii=False)

    # 연결 진단: /api/chat 에 아주 짧게 호출해 상태코드/본문을 보여준다
    def diagnose(self):
        url = f"{self.base_url}/api/chat"
        try:
            r = requests.post(url, headers=self._headers(),
                              json={"prompt": "ping", "temperature": 0.0}, timeout=self.timeout)
            try:
                text = r.text
                return {"status": r.status_code, "reason": r.reason, "text": text[:300]}
            except Exception:
                return {"status": r.status_code, "reason": r.reason, "text": "no-body"}
        except requests.RequestException as e:
            return {"status": "exception", "reason": str(e)}
