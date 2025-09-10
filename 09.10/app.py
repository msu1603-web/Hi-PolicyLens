# app.py
import os, json, time
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
        base_url = st.text_input("LLM Base URL", st.secrets.get("POTENS_BASE_URL", "https://ai.potens.ai"))
        # Potens /api/chat 방식은 모델이 필수 아니면 빈 값도 허용
        model    = st.text_input("LLM Model (선택)", st.secrets.get("POTENS_MODEL", ""))
        retriever_url = st.text_input("Retriever Base URL", st.secrets.get("RETRIEVER_BASE_URL", ""))
        top_k = st.slider("검색 Top-K (상위 근거 개수)", 4, 16, 8, 1)
        do_critic = st.checkbox("2차 검증(Critic) 사용", value=True)

    # ===== 연결 진단 =====
    with st.expander("🔌 연결 진단(LLM Endpoint)", expanded=False):
        if st.button("진단 실행", use_container_width=True):
            llm_test = LLMClient(base_url=base_url, model=model)
            info = llm_test.diagnose()  # Potens /api/chat 진단
            st.write("**/api/chat (Potens 전용)** →", info)

    # 데이터 소스 배지
    source_mode = "외부 RAG API" if retriever_url else "Mock(데모)"
    st.caption(f"데이터 소스: **{source_mode}**")

    # ===== 챗 UI =====
    if "history" not in st.session_state:
        st.session_state.history = []  # [{role, content, is_diff}]
    if "pending_query" not in st.session_state:
        st.session_state.pending_query = ""

    mode = st.radio("모드", ["일반 질의", "비교 질의"], horizontal=True)

    # --- 입력: 엔터 전송(chat_input) ---
    user_msg = st.chat_input("한국어로 질문을 입력하고 Enter를 누르세요. (예: 2020년 이후 태양광 보조금 정책 변화 요약)")

    # 기존 텍스트 버튼 방식도 병행(원하면 사용)
    manual_query = st.text_input("버튼 방식 입력 (옵션)", key="manual_query")
    do_run_btn = st.button("검색 실행", use_container_width=True)

    # 엔터 전송 또는 버튼 클릭이면 pending_query에 투입
    if user_msg:
        st.session_state.pending_query = user_msg
    elif do_run_btn and manual_query.strip():
        st.session_state.pending_query = manual_query.strip()

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

    # ===== 실행 파이프라인 =====
    if st.session_state.pending_query:
        query = st.session_state.pending_query
        st.session_state.pending_query = ""  # 소비

        # 0) 사용자 메시지 기록
        st.session_state.history.append({"role":"user","content":query})

        # 진행 상태 표시
        with st.status("검색 준비 중...", expanded=False) as status:
            status.update(label="🔎 유사 문단 검색 중...", state="running")

            # 1) 검색 컨텍스트 확보
            start = time.time()
            if retriever_url:
                retriever = RetrieverClient(base_url=retriever_url)
                chunks = retriever.search(query, k=top_k)
                def fmt(c):
                    hdr = f"[{c['doc_id']} p.{c.get('page_start','?')}-{c.get('page_end','?')} lines {c.get('line_start','?')}-{c.get('line_end','?')}]"
                    return hdr + "\n" + c["text"]
                context = "\n\n---\n\n".join(fmt(c) for c in chunks) if chunks else "(검색 결과 없음)"
            else:
                retriever = RetrieverClient(base_url="")
                chunks = retriever.search(query, k=top_k)
                def fmt(c):
                    hdr = f"[{c['doc_id']} p.{c.get('page_start','?')}-{c.get('page_end','?')} lines {c.get('line_start','?')}-{c.get('line_end','?')}]"
                    return hdr + "\n" + c["text"]
                context = "\n\n---\n\n".join(fmt(c) for c in chunks) if chunks else "(검색 결과 없음)"
            t_search = time.time() - start

            status.update(label=f"🧠 LLM 호출 중... (검색 {t_search:.1f}s)", state="running")

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
                status.update(label="❌ LLM 호출 오류", state="error")
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
                status.update(label="🧪 검증(Critic) 중...", state="running")
                critic_user = CRITIC_TEMPLATE.format(context=context, model_json=json.dumps(data, ensure_ascii=False))
                critic_raw = llm.chat_json("당신은 JSON 감사지능입니다. 출력은 JSON만.", critic_user, temperature=0.0)
                cjson = ensure_json(critic_raw)
                try:
                    judge = json.loads(cjson)
                    if not judge.get("is_valid", True) and judge.get("final"):
                        data = judge["final"]
                        st.toast("Critic 보정 적용", icon="✅")
                except Exception:
                    pass

            # 6) 출력 & 기록
            st.session_state.history.append({"role":"assistant","content":data,"is_diff":is_diff})
            status.update(label="✅ 완료", state="complete")
            st.rerun()  # 결과가 바로 위 '대화 기록'에 보이도록 새로고침
