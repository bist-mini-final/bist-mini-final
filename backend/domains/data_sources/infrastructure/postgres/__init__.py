"""PostgreSQL adapters for distributed ingestion."""

from .shards import PostgresIngestionShardRepository

__all__ = ["PostgresIngestionShardRepository"]
