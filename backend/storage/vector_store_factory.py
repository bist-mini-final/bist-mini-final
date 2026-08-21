"""VectorStore Factory for unified Multi-DB support (pgvector, Chroma, local) via LangChain."""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any, Dict, Literal, Optional

from langchain_core.vectorstores import VectorStore
from langchain_postgres import PGVector
from langchain_postgres.vectorstores import DistanceStrategy
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.core.settings import PGVECTOR_URL
from backend.providers.embeddings.factory import EmbeddingEncoder
from backend.providers.embeddings.langchain_bridge import LangChainEmbeddingAdapter

VectorDbBackend = Literal["pgvector", "local"]

# Lock to serialise the first engine creation per URL (lru_cache is not
# thread-safe during the first call for the same key).
_engine_lock = threading.Lock()


def get_langchain_connection_string(url: str = PGVECTOR_URL) -> str:
    """Convert standard postgresql:// URL to postgresql+psycopg:// for SQLAlchemy / LangChain."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=8)
def _get_cached_engine(conn_str: str) -> Engine:
    """Return a cached SQLAlchemy Engine for *conn_str*.

    The engine is created at most once per unique connection string for the
    lifetime of the process, eliminating the ~2 s overhead of repeated
    ``create_engine()`` calls.  Connection pooling is managed by SQLAlchemy's
    built-in ``QueuePool``.
    """
    return create_engine(
        conn_str,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_cached_engine(database_url: str = PGVECTOR_URL) -> Engine:
    """Thread-safe wrapper around :func:`_get_cached_engine`."""
    conn_str = get_langchain_connection_string(database_url)
    with _engine_lock:
        return _get_cached_engine(conn_str)


def get_vector_store(
    collection_name: str,
    backend: VectorDbBackend = "pgvector",
    model_name: str = "text-embedding-3-large",
    embedding_encoder: Optional[EmbeddingEncoder] = None,
    collection_metadata: Optional[Dict[str, Any]] = None,
    database_url: str = PGVECTOR_URL,
    distance_strategy: DistanceStrategy = DistanceStrategy.COSINE,
) -> VectorStore:
    """Return a standard LangChain VectorStore instance for the given backend.

    When *backend* is ``"pgvector"`` a cached SQLAlchemy :class:`Engine` is
    reused, so ``create_engine()`` is executed at most once per unique URL.
    """
    adapter = LangChainEmbeddingAdapter(
        model_name=model_name,
        encoder=embedding_encoder,
    )

    if backend == "pgvector":
        engine = get_cached_engine(database_url)
        return PGVector(
            embeddings=adapter,
            collection_name=collection_name,
            connection=engine,
            collection_metadata=collection_metadata,
            distance_strategy=distance_strategy,
            use_jsonb=True,
            create_extension=False,
        )

    raise ValueError(f"지원하지 않는 Vector DB 백엔드입니다: {backend}")
