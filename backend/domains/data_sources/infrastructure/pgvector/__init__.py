"""PostgreSQL vector adapters owned by the data-sources domain."""

from backend.platform.pgvector.errors import PgVectorStoreError
from backend.shared.application.vector import PgVectorReplacePlan

from .catalog import VECTOR_INDEX_STRATEGY, VECTOR_PARTITION_STRATEGY, PgVectorCatalogMixin
from .probe import PgVectorConnectionProbe
from .repositories import (
    PgVectorCatalogRepository,
    PgVectorIngestionRepository,
    PgVectorRepositorySet,
    PgVectorRetrievalRepository,
)
from .retrieval import PgVectorRetrievalMixin
from .store import PgVectorStore
from .writes import PGVECTOR_INSERT_BATCH_SIZE, PgVectorWriteMixin

__all__ = [
    "PGVECTOR_INSERT_BATCH_SIZE",
    "PgVectorCatalogMixin",
    "PgVectorCatalogRepository",
    "PgVectorConnectionProbe",
    "PgVectorIngestionRepository",
    "PgVectorReplacePlan",
    "PgVectorRepositorySet",
    "PgVectorRetrievalMixin",
    "PgVectorRetrievalRepository",
    "PgVectorStore",
    "PgVectorStoreError",
    "PgVectorWriteMixin",
    "VECTOR_INDEX_STRATEGY",
    "VECTOR_PARTITION_STRATEGY",
]
