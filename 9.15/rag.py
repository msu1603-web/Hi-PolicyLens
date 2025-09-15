# rag.py
import os
import re
import fitz  # PyMuPDF
import numpy as np
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

# -------- PDF → 페이지 텍스트 --------
def extract_pages(pdf_path: str) -> List[Dict]:
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        # 공백 정리
        text = re.sub(r'\s+\n', '\n', text).strip()
        pages.append({"page": i+1, "text": text})
    doc.close()
    return pages

# -------- 문장/문단 기반 청크 --------
def chunk_text(pages: List[Dict], max_chars=1200, overlap=200) -> List[Dict]:
    chunks = []
    for p in pages:
        text = p["text"]
        # 문단 단위 분할 → 길면 슬라이딩 윈도로 추가 분할
        paras = [t.strip() for t in text.split("\n\n") if t.strip()]
        for para in paras:
            if len(para) <= max_chars:
                chunks.append({"page": p["page"], "content": para})
            else:
                start = 0
                while start < len(para):
                    end = min(start + max_chars, len(para))
                    chunk = para[start:end]
                    chunks.append({"page": p["page"], "content": chunk})
                    if end == len(para):
                        break
                    start = end - overlap
    # 문장 끝 정리
    for c in chunks:
        c["content"] = clean_sentence_edges(c["content"])
    return chunks

def clean_sentence_edges(text: str) -> str:
    # 문장 중간에서 끊긴 경우를 최소화. 마침표/따옴표 기준으로 다듬기
    text = text.strip()
    # 앞뒤 공백/하이픈/쓸데없는 구두점 제거
    text = re.sub(r'^[\-\s•·]+', '', text)
    text = re.sub(r'[\-\s•·]+$', '', text)
    return text

# -------- 임베딩 & Chroma --------
class VectorStore:
    def __init__(self, persist_dir: str = "chroma_store", model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_dir
        ))
        self.collection = self.client.get_or_create_collection(name="pdf_chunks")
        self.model = SentenceTransformer(model_name)

    def reset(self):
        try:
            self.client.delete_collection("pdf_chunks")
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(name="pdf_chunks")

    def add_chunks(self, pdf_id: str, chunks: List[Dict]):
        texts = [c["content"] for c in chunks]
        metadatas = [{"page": c["page"], "pdf_id": pdf_id} for c in chunks]
        ids = [f"{pdf_id}_{i}" for i in range(len(chunks))]
        embeddings = self.model.encode(texts, convert_to_numpy=True).tolist()
        self.collection.add(documents=texts, metadatas=metadatas, ids=ids, embeddings=embeddings)
        self.client.persist()

    def query(self, q: str, k: int = 8) -> List[Dict]:
        q_emb = self.model.encode([q], convert_to_numpy=True).tolist()
        res = self.collection.query(query_embeddings=q_emb, n_results=k)
        results = []
        for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
            results.append({"content": doc, "page": meta.get("page"), "pdf_id": meta.get("pdf_id")})
        return results

# -------- 검색 결과를 "발췌" 답변으로 정리 --------
def build_extract_only_answer(hits: List[Dict]) -> str:
    if not hits:
        return "관련 정보를 찾을 수 없음"
    # 같은 페이지 인접 텍스트는 합치고, 출처(페이지) 명시
    grouped: Dict[int, List[str]] = {}
    for h in hits:
        grouped.setdefault(h["page"], []).append(h["content"].strip())

    lines = []
    for page in sorted(grouped.keys()):
        merged = merge_snippets(grouped[page])
        for snippet in merged:
            lines.append(f"[p.{page}] {snippet}")
    return "\n\n".join(lines)

def merge_snippets(snips: List[str]) -> List[str]:
    # 겹치거나 연속된 느낌의 스니펫 합치기(단순 규칙)
    out = []
    buffer = ""
    for s in snips:
        if not buffer:
            buffer = s
        else:
            # 문장 이어붙이기: 문장부호/줄바꿈 기준으로 자연스럽게
            if len(buffer) < 800 and (buffer.endswith("…") or buffer.endswith("—") or not buffer[-1] in ".!?\"”’"):
                buffer += " " + s
            else:
                out.append(buffer.strip())
                buffer = s
    if buffer:
        out.append(buffer.strip())
    return out
