"""Explicit factory boundary for probing user-supplied pgvector endpoints."""

from __future__ import annotations

from typing import Any

from .store import PgVectorStore


class PgVectorConnectionProbe:
    """Create a short-lived adapter only for an explicit connection probe."""

    def inspect(self, database_url: str) -> dict[str, Any]:
        return PgVectorStore(database_url).get_db_info()


__all__ = ["PgVectorConnectionProbe"]
