# app.py
import os, json
import streamlit as st
import pandas as pd

from llm_client import LLMClient
from retriever_client import RetrieverClient
from prompts import SYSTEM_POLICY, USER_QA_TEMPLATE, USER_DIFF_TEMPLATE, CRITIC_TEMPLATE

st.set_page_config(page_title="신재생 정책·규제 원문 인용 검색", layout="wide")
st.title("🔎 신재생에너지 정책·규제 — 원문 인용 스마트 검색")

# ====================== 레이아웃: 좌(2/3) PDF, 우(1/3) 챗봇 ======================
left, right = st.columns([2, 1], gap="large")

# ---------- 좌측: PDF 미리보기 ----------
with left:
    st.subheader("📄 원문 PDF 미리보기")
    pdf_files = st.file_uploader(
        "여러 PDF를 업로드하세요 (미리보기 전용 · 검색 엔진과는 별개)", type=["pdf"], accept_multiple_files=True
    )
    if "pdf_buffers" not in st.session_state:
        st.session_state.pdf_buffers = {}

    if pdf_files:
        names = []
        for f in pdf_files:
            names.append(f.name)
            st.session_state.pdf_buffers[f.name] = f.getvalue()
        pick = st.selectbox("보기 원하는 파일 선택", names, index=0)
        # Streamlit 1.36+ 에서 st.pdf 지원
        try:
            st.pdf(st.session_state.pdf_buffers[pick], height=900)
        except Exception:
            st.info("브라우저/버전에 따라 미리보기가 제한될 수 있어요. 아래 버튼으로 내려받아 확인하세요.")
            st.download_button("선택 PDF 다운로드", st.session_state.pdf_buffers[pick], file_name=pick)
    else:
        st.caption("여기에 참고용 PDF를 올리면 화면 2/3 영역에 미리보기가 표시됩니다. (현재 검색은 팀원 RAG API 또는 Mock 텍스트 사용)")

# ---------- 우측: 챗봇/설정 ----------
with right:
    st.subheader("🧠 AI 검색")

    # ===== 설정 =====
    with st.expander("설정", expanded=True):
        base_url = st.text_input("LLM Base URL", st.secrets.get("POTENS_BASE_URL", "https://api.potens.ai"))
        model    = st.text_input("LLM Model", st.secrets.get("POTENS_MODEL", "claude-3-5-sonnet-20240620"))
        retriever_url = st.text_input("Retriever Base URL", st.secrets.get("RETRIEVER_BASE_URL", ""))
        top_k = st.slider("검색 Top-K (상위 근거 개수)", 4, 16, 8, 1)
        do_critic = st.checkbox("2차 검증(Critic) 사용", value=True)

    # ===== LLM 연결 진단 =====
    with st.expander("🔌 연결 진단(LLM Endpoint)", expanded=False):
        if st.button("진단 실행", use_container_width=True):
            llm_test = LLMClient(base_url=base_url, model=model)
            info = llm_test.diagnose()
            st.write("**/v1/chat/completions (OpenAI 호환)** →", info.get("openai_compatible"))
            st.write("**/v1/messages (Anthropic 스타일)** →", info.get("anthropic_style"))
            st.caption("status 200이면 OK. 401=키/권한, 404=경로, 400=모델명/파라미터 오류 가능성이 큽니다.")

    # ===== 챗 UI =====
    if "history" not in st.session_state:
        st.session_state.history = []  # [{role, content, is_diff}]

    mode = st.radio("모드", ["일반 질의", "비교 질의"], horizontal=True)
    placeholder = "여기에 한국어로 질문을 입력하세요. (예: 2020년 이후 태양광 보조금 정책 변화 요약)"
    query = st.text_input(placeholder)

    # ==== 유틸 ====
    def ensure_json(txt):
        s = txt.find("{"); e = txt.rfind("}")
        return txt[s:e+1] if s>=0 and e>s else txt

    def render_json_answer(data, is_diff=False):
        st.markdown("**요약 답변**")
        st.write(data.get("answer", "(answer 없음)"))

        if "timeline" in data:
            st.markdown("**변화 타임라인**")
            df = pd.DataFrame(data.get("timeline", []))
            if not df.empty: st.dataframe(df, use_container_width=True)

        if is_diff:
            st.markdown("**차이 표(diff_table)**")
            ddf = pd.DataFrame(data.get("diff_table", []))
            if not ddf.empty: st.dataframe(ddf, use_container_width=True)
            st.markdown("**누락/불확실**")
            st.write(data.get("missing_info", "(없음)"))

        st.markdown("**근거 인용(원문 그대로)**")
        qdf = pd.DataFrame(data.get("quotes", []))
        if not qdf.empty: st.dataframe(qdf, use_container_width=True)

    # 이전 대화 출력
    if st.session_state.history:
        st.divider()
        st.caption("대화 기록")
        for turn in st.session_state.history:
            if turn["role"] == "user":
                st.write("🙋‍♀️ ", turn["content"])
            else:
                render_json_answer(turn["content"], is_diff=turn.get("is_diff", False))

    # ===== 실행 =====
    if st.button("검색 실행", use_container_width=True) and query.strip():
        # 1) 검색 컨텍스트 확보
        if retriever_url:
            # 팀원 검색 API 사용
            retriever = RetrieverClient(base_url=retriever_url)
            chunks = retriever.search(query, k=top_k)
            def fmt(c):
                hdr = f"[{c['doc_id']} p.{c.get('page_start','?')}-{c.get('page_end','?')} lines {c.get('line_start','?')}-{c.get('line_end','?')}]"
                return hdr + "\n" + c["text"]
            context = "\n\n---\n\n".join(fmt(c) for c in chunks) if chunks else "(검색 결과 없음)"
        else:
            # 외부 검색 API 미연결 시: retriever_client 의 Mock 텍스트 사용
            retriever = RetrieverClient(base_url="")
            chunks = retriever.search(query, k=top_k)
            def fmt(c):
                hdr = f"[{c['doc_id']} p.{c.get('page_start','?')}-{c.get('page_end','?')} lines {c.get('line_start','?')}-{c.get('line_end','?')}]"
                return hdr + "\n" + c["text"]
            context = "\n\n---\n\n".join(fmt(c) for c in chunks) if chunks else "(검색 결과 없음)"

        # 2) 프롬프트 (한국어 강제)
        if mode == "일반 질의":
            user_prompt = USER_QA_TEMPLATE.format(question=query, context=context, k=top_k)
            is_diff = False
        else:
            user_prompt = USER_DIFF_TEMPLATE.format(question=query, context=context, k=top_k)
            is_diff = True

        # 3) LLM 호출
        llm = LLMClient(base_url=base_url, model=model)
        raw = llm.chat_json(SYSTEM_POLICY + "\n모든 출력은 한국어로 작성하세요.", user_prompt, temperature=0.2)

        # └ 연결 오류(JSON 문자열에 _error 포함)면 그대로 표기하고 종료
        if raw.strip().startswith("{") and '"_error"' in raw:
            st.error("LLM 호출 오류 상세")
            st.code(raw, language="json")
            st.stop()

        raw_json = ensure_json(raw)

        # 4) 파싱
        try:
            data = json.loads(raw_json)
        except Exception:
            data = {"answer":"JSON 파싱 실패. 모델 응답 원문을 확인하세요.", "quotes":[], "raw":raw}

        # 5) Critic (선택)
        if do_critic:
            critic_user = CRITIC_TEMPLATE.format(context=context, model_json=json.dumps(data, ensure_ascii=False))
            critic_raw = llm.chat_json("당신은 JSON 감사지능입니다. 출력은 JSON만.", critic_user, temperature=0.0)
            cjson = ensure_json(critic_raw)
            try:
                judge = json.loads(cjson)
                if not judge.get("is_valid", True) and judge.get("final"):
                    data = judge["final"]
                    st.info("🧪 Critic 보정 적용")
            except Exception:
                pass

        # 6) 출력 & 기록
        st.session_state.history.append({"role":"user","content":query})
        st.session_state.history.append({"role":"assistant","content":data,"is_diff":is_diff})
        st.success("완료! 위의 대화 기록에 결과가 추가되었습니다.")
