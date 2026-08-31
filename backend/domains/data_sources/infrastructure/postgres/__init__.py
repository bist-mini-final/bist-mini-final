"""PostgreSQL adapters for distributed ingestion."""

from .schema import DATA_SOURCE_SCHEMA_SQL
from .shards import PostgresIngestionShardRepository
from .source_files import PostgresSourceFileRepository

__all__ = [
    "DATA_SOURCE_SCHEMA_SQL",
    "PostgresIngestionShardRepository",
    "PostgresSourceFileRepository",
]
