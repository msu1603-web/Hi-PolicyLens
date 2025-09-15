import os
import io
import time
import urllib.request
import tempfile
import pandas as pd
import numpy as np
import streamlit as st
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.utils import embedding_functions
from utils import extract_pdf_text_with_pages, build_chunks, extract_verbatim_quotes, dedupe_preserve_order

st.set_page_config(page_title="PDF 원문 발췌 QA", page_icon="📑", layout="wide")

DB_DIR = "db"
os.makedirs("data", exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

# -------- Sidebar: 업로드/색인 --------
st.sidebar.header("① 문서 업로드 & 색인")
uploaded = st.sidebar.file_uploader("PDF 업로드(.pdf)", type=["pdf"], accept_multiple_files=True)
url_input = st.sidebar.text_input("PDF URL 붙여넣기(선택)")

if "embed_model" not in st.session_state:
    st.session_state.embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
if "chroma" not in st.session_state:
    st.session_state.client = chromadb.PersistentClient(path=DB_DIR)
    st.session_state.collection = st.session_state.client.get_or_create_collection(
        name="pdf_quotes",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    )

def index_pdf(path: str, doc_id_prefix: str):
    pages = extract_pdf_text_with_pages(path)
    chunks = build_chunks(pages, window_sentences=6, stride=3)
    if not chunks:
        return 0

    # Chroma에 저장
    ids = []
    docs = []
    metas = []
    for i, ch in enumerate(chunks):
        ids.append(f"{doc_id_prefix}-{i}")
        docs.append(ch["text"])
        metas.append({"page": ch["page"], "source": os.path.basename(path)})

    st.session_state.collection.add(ids=ids, documents=docs, metadatas=metas)
    return len(chunks)

colL, colR = st.columns(2)
with colL:
    if uploaded:
        for f in uploaded:
            save_path = os.path.join("data", f.name)
            with open(save_path, "wb") as out:
                out.write(f.read())
            n = index_pdf(save_path, doc_id_prefix=f.name)
            st.success(f"{f.name} 색인 완료: {n}개 청크")
with colR:
    if url_input:
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            urllib.request.urlretrieve(url_input, tmp.name)
            name = url_input.split("/")[-1].split("?")[0] or f"url_{int(time.time())}.pdf"
            save_path = os.path.join("data", name)
            os.replace(tmp.name, save_path)
            n = index_pdf(save_path, doc_id_prefix=name)
            st.success(f"URL 문서 색인 완료: {name} / {n}개 청크")
        except Exception as e:
            st.error(f"URL 다운로드 실패: {e}")

st.sidebar.divider()
st.sidebar.caption("※ 스캔(이미지) PDF는 텍스트 추출이 어려울 수 있습니다(초기 버전은 OCR 미지원).")

# -------- Main: 질문 → 원문 발췌 --------
st.header("📑 PDF 원문 발췌 QA (요약/창작 금지)")
query = st.text_input("질문을 입력하세요 (예: 올해 태양광 투자 계획은 어떻게 돼?)")
top_k = st.number_input("검색 청크 개수 (k)", min_value=3, max_value=50, value=10)

def search_and_quote(question: str, k: int = 10, max_quotes: int = 8):
    if st.session_state.collection.count() == 0:
        return [], []
    # 1) 벡터 검색
    out = st.session_state.collection.query(query_texts=[question], n_results=k)
    docs = out.get("documents", [[]])[0]
    metas = out.get("metadatas", [[]])[0]

    # 2) 각 청크에서 '문장 단위'로 정확 인용 추출
    quotes = []
    rows = []
    for doc, meta in zip(docs, metas):
        qts = extract_verbatim_quotes(doc, question, topk=3)
        for q in qts:
            quotes.append(q)
            rows.append({
                "인용문": q,
                "페이지": meta.get("page"),
                "문서": meta.get("source")
            })
            if len(quotes) >= max_quotes:
                break
        if len(quotes) >= max_quotes:
            break

    # 3) 중복 제거 & 결과 표
    dq = dedupe_preserve_order(quotes)
    df = pd.DataFrame(rows)
    return dq, df

if st.button("🔎 원문 발췌 찾기", type="primary"):
    if not query.strip():
        st.warning("질문을 입력하세요.")
    else:
        quotes, table = search_and_quote(query, k=int(top_k))
        if not quotes:
            st.error("관련 정보를 찾을 수 없음 (문서에 해당 내용이 없거나, 스캔 PDF로 텍스트가 추출되지 않았을 수 있습니다).")
        else:
            st.success(f"원문 인용 {len(quotes)}건")
            for i, q in enumerate(quotes, start=1):
                st.markdown(f"**{i}.** “{q}”")
            st.dataframe(table, use_container_width=True)
            csv = table.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ CSV로 내보내기", data=csv, file_name="quotes.csv", mime="text/csv")

st.caption("※ 본 도구는 원문 ‘그대로’ 인용만 제공합니다. 문서에 없으면 ‘관련 정보를 찾을 수 없음’으로 표시됩니다.")
