"""Connection capabilities shared by composed PostgreSQL repository mixins."""

from __future__ import annotations

from typing import Any


class DatabaseConnectionCapability:
    """Structural base supplied by DatabaseManager at the composition boundary."""

    database_url: str

    def _raw_connection(self) -> Any:
        raise NotImplementedError

    def _advisory_lock_connection(self) -> Any:
        raise NotImplementedError


class PgVectorConnectionCapability:
    """Connection and collection lookup surface supplied by PgVectorStore."""

    database_url: str
    _collection_uuid_cache: dict[str, str]
    _collection_uuid_lock: Any

    def _raw_connection(self) -> Any:
        raise NotImplementedError

    def _read_connection(self) -> Any:
        raise NotImplementedError

    def _collection_uuid(self, collection_name: str) -> str | None:
        raise NotImplementedError

    async def _collection_uuid_async(self, collection_name: str) -> str | None:
        raise NotImplementedError

    def _drop_collection_vector_index(
        self,
        collection_uuid: str,
        dimension: int,
    ) -> None:
        raise NotImplementedError

    def ensure_optimized_indexes(self) -> None:
        raise NotImplementedError


__all__ = ["DatabaseConnectionCapability", "PgVectorConnectionCapability"]
