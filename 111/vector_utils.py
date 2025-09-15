from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.utils import embedding_functions

model = SentenceTransformer("all-MiniLM-L6-v2")
chroma_client = chromadb.Client()
collection = chroma_client.get_or_create_collection("pdf_chunks")

def embed_and_store_chunks(chunks):
    embeddings = model.encode(chunks).tolist()
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        collection.add(documents=[chunk], embeddings=[emb], ids=[str(i)])

def search_similar_chunks(question, top_k=3):
    question_emb = model.encode([question]).tolist()
    results = collection.query(query_embeddings=question_emb, n_results=top_k)
    if results["documents"]:
        return results["documents"][0]
    else:
        return []
