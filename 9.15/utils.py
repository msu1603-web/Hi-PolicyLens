import re
from typing import List, Dict, Tuple
from pypdf import PdfReader

SENT_SPLIT = re.compile(r"(?<=[.!?。．])\s+")

def extract_pdf_text_with_pages(path: str) -> List[Dict]:
    """PDF에서 페이지별 텍스트 추출"""
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"\s+", " ", text).strip()
        pages.append({"page": i, "text": text})
    return pages

def split_sentences(text: str) -> List[str]:
    if not text:
        return []
    # 문장 단위로 잘라 원문 인용이 정확히 되도록 함
    parts = SENT_SPLIT.split(text)
    # 너무 짧은 조각 제거
    return [p.strip() for p in parts if len(p.strip()) > 3]

def build_chunks(pages: List[Dict], window_sentences: int = 6, stride: int = 3) -> List[Dict]:
    """
    문장 기반 슬라이딩 윈도우 청크 (페이지 정보 포함).
    - 요약/창작 금지 → 원문 문장 그대로 담긴 덩어리를 만들기 위함
    """
    chunks = []
    for p in pages:
        sents = split_sentences(p["text"])
        if not sents:
            continue
        i = 0
        while i < len(sents):
            chunk_sents = sents[i:i+window_sentences]
            chunk_text = " ".join(chunk_sents)
            chunks.append({"page": p["page"], "text": chunk_text})
            if i + window_sentences >= len(sents):
                break
            i += stride
    return chunks

def extract_verbatim_quotes(chunk_text: str, question: str, topk: int = 3) -> List[str]:
    """
    청크 안에서 '질문과 연관 키워드'가 들어간 문장만 그대로 발췌.
    - BM25를 쓰면 더 좋지만, 간단히 키워드 기반 필터도 병행
    """
    # 키워드 후보: 질문에서 2자 이상 토큰만
    toks = [t.lower() for t in re.findall(r"[A-Za-z0-9가-힣]+", question) if len(t) >= 2]
    sents = split_sentences(chunk_text)
    scored = []
    for s in sents:
        low = s.lower()
        hit = sum(1 for t in toks if t in low)
        if hit > 0:
            scored.append((hit, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:topk]]

def dedupe_preserve_order(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
