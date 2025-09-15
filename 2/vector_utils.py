# vector_utils.py

# --- (A) sqlite 대체: Streamlit Cloud에서 chromadb가 sqlite 의존성으로 자주 터짐 ---
try:
    import sys, importlib
    import pysqlite3  # noqa: F401  # ensure installed
    sys.modules["sqlite3"] = importlib.import_module("pysqlite3")
except Exception:
    # 로컬 등 정상 환경이면 그냥 패스
    pass

# --- (B) 임포트 ---
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

# --- (C) Chroma 클라이언트: duckdb+parquet + 쓰기 가능한 경로(/tmp) 사용 ---
#   - Streamlit Cloud에서는 현재 작업 디렉토리에 쓰기 권한이 제한적일 수 있어 /tmp 권장
client = chromadb.Client(
    Settings(
        chroma_db_impl="duckdb+parquet",
        persist_directory="/tmp/chroma_db"  # 세션 동안 유지
    )
)

# 컬렉션 생성(이름 고정)
collection = client.get_or_create_collection(name="pdf_chunks")

# --- (D) 임베딩 모델 ---
model = SentenceTransformer("all-MiniLM-L6-v2")

# --- (E) 함수들 ---
def embed_and_store_chunks(chunks):
    """chunks를 임베딩하여 chroma에 저장"""
    if not chunks:
        return
    embeddings = model.encode(chunks).tolist()

    # 같은 앱 세션에서 재업로드 시 id 충돌 방지: 기존 컬렉션 비우고 새로 넣기
    # (문서 여러 개 관리하려면 doc_id/메타데이터로 확장하세요)
    try:
        # 전체 삭제 (0.4.x에선 where 지원 X, 그래서 reset 방식)
        # 가장 안전하게: 컬렉션을 없앴다 재생성
        client.delete_collection("pdf_chunks")
    except Exception:
        pass
    col = client.get_or_create_collection(name="pdf_chunks")

    ids = [f"chunk-{i}" for i in range(len(chunks))]
    col.add(documents=chunks, embeddings=embeddings, ids=ids)


def search_similar_chunks(question, top_k=3):
    """질문과 유사한 청크들을 반환"""
    question_emb = model.encode([question]).tolist()[0]
    col = client.get_or_create_collection(name="pdf_chunks")
    res = col.query(query_embeddings=[question_emb], n_results=top_k)
    if res and res.get("documents") and res["documents"][0]:
        return res["documents"][0]
    return []
