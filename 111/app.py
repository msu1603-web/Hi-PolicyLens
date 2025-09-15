import streamlit as st
from pdf_utils import extract_text_from_pdf, chunk_text
from vector_utils import embed_and_store_chunks, search_similar_chunks

st.set_page_config(page_title="정부 보고서 AI 분석기", layout="wide")
st.title("📑 정부 보고서 AI 분석기")

uploaded_pdf = st.file_uploader("PDF 파일을 업로드하세요", type="pdf")

if uploaded_pdf:
    with st.spinner("PDF에서 텍스트 추출 중..."):
        text = extract_text_from_pdf(uploaded_pdf)
        chunks = chunk_text(text)
        embed_and_store_chunks(chunks)
    st.success("✅ PDF 분석 완료! 아래에 질문을 입력하세요.")

    query = st.text_input("궁금한 내용을 입력하세요", placeholder="예: 올해 태양광 투자 계획은?")
    if query:
        with st.spinner("관련 내용을 찾고 있어요..."):
            results = search_similar_chunks(query)
            if results:
                st.markdown("### 🔍 관련 문서 내용")
                for res in results:
                    st.write(f"• {res}")
            else:
                st.warning("❗ 관련 정보를 찾을 수 없습니다.")
