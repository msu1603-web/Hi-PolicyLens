# app.py
import os
import streamlit as st
import tempfile
from rag import extract_pages, chunk_text, VectorStore, build_extract_only_answer
import requests

st.set_page_config(page_title="PDF 발췌 RAG", layout="wide")

st.title("📄 PDF 질의·응답 (원문 '그대로 발췌' 전용)")

# --- 사이드바: 인덱싱 ---
with st.sidebar:
    st.header("① PDF 업로드 & 인덱싱")
    uploaded = st.file_uploader("PDF 파일 업로드", type=["pdf"])
    build_index = st.button("인덱스 생성/초기화")

    st.divider()
    st.header("② (선택) 포텐스 API")
    use_potens = st.checkbox("포텐스 API로 발췌문 형식화(요약 금지)", value=False)
    pot_endpoint = "https://ai.potens.ai/api/chat"
    pot_key = st.secrets.get("POTENS_API_KEY", None)
    if use_potens and not pot_key:
        st.warning("⚠️ Streamlit Secrets에 POTENS_API_KEY 를 넣어주세요.")

# --- 전역: 벡터 스토어 준비 ---
VS_DIR = "chroma_store"
vs = VectorStore(persist_dir=VS_DIR)

# 인덱싱 단계
if uploaded and build_index:
    vs.reset()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    with st.status("PDF에서 텍스트 추출 중...", expanded=False):
        pages = extract_pages(tmp_path)

    with st.status("청크 분할 및 임베딩 중...", expanded=False):
        chunks = chunk_text(pages, max_chars=1200, overlap=200)
        vs.add_chunks(pdf_id=os.path.basename(tmp_path), chunks=chunks)

    st.success(f"인덱스 완료! 총 {len(chunks)}개 청크를 추가했습니다.")
    os.remove(tmp_path)

# --- 메인: 질의/발췌 ---
st.header("질문하기")
q = st.text_input("예) 올해 태양광 투자 계획은 어떻게 돼?")
k = st.slider("검색할 청크 개수 (k)", 3, 15, 8)

if st.button("검색 실행"):
    if not q.strip():
        st.warning("질문을 입력하세요.")
    else:
        hits = vs.query(q, k=k)
        answer = build_extract_only_answer(hits)

        # 화면에 원문 발췌 바로 보여주기
        st.subheader("🔎 원문 발췌 결과")
        if answer == "관련 정보를 찾을 수 없음":
            st.info(answer)
        else:
            st.code(answer, language="markdown")

        # (선택) 포텐스 API로 "발췌만" 형식화
        if use_potens and pot_key:
            st.subheader("🛠 포텐스 API 형식화(요약 금지)")
            prompt = f"""당신은 편집 보조자입니다.
아래 '검색 발췌' 텍스트만 사용해 질문에 답하세요. 
규칙:
- 원문 문장만 그대로 복사해서 사용하고, 임의 요약/의역 금지
- 인용 문장 앞에 반드시 페이지 표기 [p.xx]를 유지
- 문서에 없으면 '관련 정보를 찾을 수 없음'이라고만 답변

[질문]
{q}

[검색 발췌]
{answer}
"""
            try:
                res = requests.post(
                    pot_endpoint,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {st.secrets['POTENS_API_KEY']}"
                    },
                    json={"prompt": prompt},
                    timeout=60
                )
                res.raise_for_status()
                out = res.json()
                # API 응답 포맷에 맞게 수정 필요할 수 있음 (샘플)
                llm_text = out.get("text") or out.get("response") or str(out)
                st.code(llm_text, language="markdown")
            except Exception as e:
                st.error(f"포텐스 API 호출 실패: {e}")
