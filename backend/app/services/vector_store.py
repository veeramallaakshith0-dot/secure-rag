from functools import lru_cache
from pathlib import Path

from qdrant_client import QdrantClient, models
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
COLLECTION_NAME = "secure_rag_chunks"


@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    if settings.qdrant_url:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    else:
        path = BACKEND_DIR / settings.qdrant_path
        path.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(path))
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=settings.embedding_dimension, distance=models.Distance.COSINE),
        )
    client.create_payload_index(COLLECTION_NAME, "owner_id", field_schema=models.PayloadSchemaType.INTEGER)
    client.create_payload_index(COLLECTION_NAME, "document_id", field_schema=models.PayloadSchemaType.INTEGER)
    client.create_payload_index(COLLECTION_NAME, "tags", field_schema=models.PayloadSchemaType.KEYWORD)
    return client


@lru_cache(maxsize=1)
def get_embedder() -> HuggingFaceEmbedding:
    return HuggingFaceEmbedding(model_name=settings.embedding_model, device="cpu", normalize=True)
