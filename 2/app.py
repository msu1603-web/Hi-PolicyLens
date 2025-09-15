# app.py
import streamlit as st
from pdf_utils import extract_text_from_pdf, chunk_text
from vector_utils import embed_and_store_chunks, search_similar_chunks

st.set_page_config(page_title="정부 보고서 AI 분석기", layout="wide")
st.title("📑 정부 보고서 AI 분석기")

with st.expander("상태 체크(문제가 있으면 여기부터 확인)", expanded=False):
    st.write("이 문장이 보이면 앱은 정상 구동 중입니다.")

uploaded_pdf = st.file_uploader("PDF 파일 업로드", type=["pdf"])

if uploaded_pdf is not None:
    with st.spinner("PDF 텍스트 추출 중..."):
        text = extract_text_from_pdf(uploaded_pdf)
        if not text.strip():
            st.error("PDF에서 텍스트를 추출하지 못했습니다. (이미지 기반 PDF일 수 있음)")
        else:
            chunks = chunk_text(text)
            embed_and_store_chunks(chunks)
            st.success(f"✅ 분석 완료! 청크 수: {len(chunks)}")

    query = st.text_input("질문을 입력하세요 (예: 올해 태양광 투자 계획은?)")
    if query:
        with st.spinner("문서에서 관련 원문을 찾는 중..."):
            results = search_similar_chunks(query)
            if results:
                st.subheader("🔍 관련 원문 발췌")
                for i, r in enumerate(results, 1):
                    st.markdown(f"**{i}.** {r}")
            else:
                st.warning("❗ 관련 정보를 찾을 수 없습니다.")
else:
    st.info("왼쪽에 PDF를 업로드하면 시작합니다.")
