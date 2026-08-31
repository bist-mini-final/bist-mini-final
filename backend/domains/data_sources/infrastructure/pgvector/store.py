"""Native psycopg storage adapter for PostgreSQL and pgvector."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional
from uuid import UUID

from backend.core.settings import PGVECTOR_URL
from backend.platform.pgvector.errors import PgVectorStoreError
from backend.platform.postgres.pool import (
    get_pooled_async_connection,
    get_pooled_raw_connection,
)
from backend.shared.application.vector import PgVectorReplacePlan

from .catalog import (
    VECTOR_INDEX_STRATEGY,
    VECTOR_PARTITION_STRATEGY,
    PgVectorCatalogMixin,
)
from .retrieval import PgVectorRetrievalMixin
from .writes import (
    PGVECTOR_INSERT_BATCH_SIZE,
    PgVectorWriteMixin,
)


class PgVectorStore(
    PgVectorWriteMixin,
    PgVectorCatalogMixin,
    PgVectorRetrievalMixin,
):
    """Manage pgvector collections through the shared psycopg connection pool."""

    @staticmethod
    def index_id(artifact_id: str) -> str:
        """Derive standard pgvector collection index identifier from an artifact ID."""
        return f"idx_{artifact_id}"

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self.database_url = database_url
        self._collection_uuid_cache: Dict[str, str] = {}
        self._collection_uuid_lock = threading.Lock()

    def _raw_connection(self) -> Any:
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://", "postgresql://"
        )
        return get_pooled_raw_connection(raw_url)

    def _read_connection(self) -> Any:
        """Borrow an autocommit connection so SELECTs avoid a rollback round trip."""
        connection = self._raw_connection()
        connection.autocommit = True
        return connection

    def _collection_uuid(self, collection_name: str) -> Optional[str]:
        """Resolve and cache a collection UUID to remove a lookup from hot searches."""
        cached = self._collection_uuid_cache.get(collection_name)
        if cached is not None:
            return cached
        connection = self._read_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT uuid FROM langchain_pg_collection WHERE name = %s;",
                    (collection_name,),
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        # The canonical UUID representation is also safe to embed in a query
        # predicate when selecting a collection-local partial index.
        resolved = str(UUID(str(row[0])))
        with self._collection_uuid_lock:
            self._collection_uuid_cache[collection_name] = resolved
        return resolved

    async def _collection_uuid_async(self, collection_name: str) -> Optional[str]:
        """Resolve collection identity without blocking the workflow event loop."""
        cached = self._collection_uuid_cache.get(collection_name)
        if cached is not None:
            return cached
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://",
            "postgresql://",
        )
        async with get_pooled_async_connection(raw_url) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT uuid FROM langchain_pg_collection WHERE name = %s;",
                    (collection_name,),
                )
                row = await cursor.fetchone()
        if row is None:
            return None
        resolved = str(UUID(str(row[0])))
        with self._collection_uuid_lock:
            self._collection_uuid_cache[collection_name] = resolved
        return resolved


__all__ = [
    "PGVECTOR_INSERT_BATCH_SIZE",
    "PgVectorReplacePlan",
    "PgVectorStore",
    "PgVectorStoreError",
    "VECTOR_INDEX_STRATEGY",
    "VECTOR_PARTITION_STRATEGY",
]
