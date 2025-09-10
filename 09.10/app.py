import os, json
import streamlit as st
import pandas as pd

from llm_client import LLMClient
from retriever_client import RetrieverClient
from prompts import SYSTEM_POLICY, USER_QA_TEMPLATE, USER_DIFF_TEMPLATE, CRITIC_TEMPLATE

st.set_page_config(page_title="신재생 정책·규제 원문 인용 검색", layout="wide")
st.title("🔎 신재생에너지 정책·규제 — 원문 인용 스마트 검색")

with st.sidebar:
    st.subheader("⚙️ 설정")
    base_url = st.text_input("LLM Base URL", st.secrets.get("POTENS_BASE_URL", "https://api.potens.ai"))
    model    = st.text_input("LLM Model", st.secrets.get("POTENS_MODEL", "claude-4-sonnet"))
    retriever_url = st.text_input("Retriever Base URL", st.secrets.get("RETRIEVER_BASE_URL", ""))
    top_k = st.slider("검색 Top-K", 4, 16, 8, 1)
    do_critic = st.checkbox("2차 검증(Critic) 사용", value=True)
    st.caption("🔒 API 키는 .streamlit/secrets.toml에만 보관하세요. 깃허브에 올리지 마세요.")

if "history" not in st.session_state:
    st.session_state.history = []  # [{role, content, is_diff}]

mode = st.radio("모드", ["일반 질의", "비교 질의"], horizontal=True)
query = st.chat_input("자연어로 질문하세요. (예: 태양광 보조금 정책 변화 알려줘)")

def format_context(chunks):
    if not chunks: return "(검색 결과 없음)"
    blocks = []
    for c in chunks:
        hdr = f"[{c['doc_id']} p.{c.get('page_start','?')}-{c.get('page_end','?')} lines {c.get('line_start','?')}-{c.get('line_end','?')}]"
        blocks.append(hdr + "\n" + c["text"])
    return "\n\n---\n\n".join(blocks)

def ensure_json(txt):
    s = txt.find("{"); e = txt.rfind("}")
    return txt[s:e+1] if s>=0 and e>s else txt

def render_json_answer(data, is_diff=False):
    st.subheader("요약 답변")
    st.write(data.get("answer", "(answer 없음)"))

    if "timeline" in data:
        st.subheader("변화 타임라인")
        df = pd.DataFrame(data.get("timeline", []))
        if not df.empty: st.dataframe(df, use_container_width=True)

    if is_diff:
        st.subheader("차이 표 (diff_table)")
        ddf = pd.DataFrame(data.get("diff_table", []))
        if not ddf.empty: st.dataframe(ddf, use_container_width=True)
        st.subheader("누락/불확실")
        st.write(data.get("missing_info", "(없음)"))

    st.subheader("근거 인용(원문 그대로)")
    qdf = pd.DataFrame(data.get("quotes", []))
    if not qdf.empty: st.dataframe(qdf, use_container_width=True)

# 과거 대화 출력
for turn in st.session_state.history:
    with st.chat_message(turn["role"]):
        if turn["role"] == "assistant" and isinstance(turn["content"], dict):
            render_json_answer(turn["content"], turn.get("is_diff", False))
        else:
            st.write(turn["content"])

if query:
    st.session_state.history.append({"role":"user","content":query})
    with st.chat_message("user"): st.write(query)

    # 1) 검색
    retriever = RetrieverClient(base_url=retriever_url)
    chunks = retriever.search(query, k=top_k)
    context = format_context(chunks)

    # 2) 프롬프트
    if mode == "일반 질의":
        user_prompt = USER_QA_TEMPLATE.format(question=query, context=context, k=top_k)
        is_diff = False
    else:
        user_prompt = USER_DIFF_TEMPLATE.format(question=query, context=context, k=top_k)
        is_diff = True

    # 3) LLM 호출
    llm = LLMClient(base_url=base_url, model=model)
    raw = llm.chat_json(SYSTEM_POLICY, user_prompt, temperature=0.2)
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
    with st.chat_message("assistant"):
        render_json_answer(data, is_diff=is_diff)
    st.session_state.history.append({"role":"assistant","content":data,"is_diff":is_diff})
