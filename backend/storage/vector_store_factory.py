"""VectorStore Factory for unified Multi-DB support (pgvector, Chroma, local) via LangChain."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from langchain_postgres import PGVector
from langchain_postgres.vectorstores import DistanceStrategy

from ..core.settings import PGVECTOR_URL
from ..embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from ..embeddings.langchain_bridge import LangChainEmbeddingAdapter

VectorDbBackend = Literal["pgvector", "local"]


def get_langchain_connection_string(url: str = PGVECTOR_URL) -> str:
    """Convert standard postgresql:// URL to postgresql+psycopg:// for SQLAlchemy / LangChain."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def get_vector_store(
    collection_name: str,
    backend: VectorDbBackend = "pgvector",
    model_name: str = "text-embedding-3-large",
    embedding_encoder: Optional[EmbeddingEncoder] = None,
    database_url: str = PGVECTOR_URL,
    distance_strategy: DistanceStrategy = DistanceStrategy.COSINE,
) -> VectorStore:
    """Return a standard LangChain VectorStore instance for the given backend."""
    adapter = LangChainEmbeddingAdapter(
        model_name=model_name,
        encoder=embedding_encoder,
    )

    if backend == "pgvector":
        conn_str = get_langchain_connection_string(database_url)
        return PGVector(
            embeddings=adapter,
            collection_name=collection_name,
            connection=conn_str,
            distance_strategy=distance_strategy,
            use_jsonb=True,
            create_extension=True,
        )

    raise ValueError(f"지원하지 않는 Vector DB 백엔드입니다: {backend}")
