# pinecone_sdk.py

import os
from dotenv import load_dotenv
from pinecone import Pinecone
from upload_processor import get_embedding_model

load_dotenv()

# ✅ Create Pinecone client instance
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# ✅ Connect to existing index
index_name = "smartai-transcripts"
if index_name not in pc.list_indexes().names():
    raise ValueError(
        f"Index '{index_name}' not found. Available: {pc.list_indexes().names()}")

index = pc.Index(index_name)
print(f"📡 Connected to Pinecone index: {index_name}")


def search_similar_chunks(query: str, top_k: int = 5):
    # Get embedding for query
    embedder = get_embedding_model()
    query_vector = embedder.embed_query(query)

    # Query Pinecone index
    results = index.query(vector=query_vector,
                          top_k=top_k, include_metadata=True)

    chunks = []
    for match in results.matches:
        chunks.append({
            "text": match.metadata.get("text", ""),
            "score": match.score
        })

    return chunks
