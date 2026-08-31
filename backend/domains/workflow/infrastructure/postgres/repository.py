"""Composed PostgreSQL repository for workflow persistence capabilities."""

from __future__ import annotations

from typing import Any

from backend.core.settings import PGVECTOR_URL
from backend.platform.postgres.pool import get_pooled_async_connection
from backend.platform.postgres.repositories import SyncPostgresRepository

from .history import WorkflowRunHistoryRepositoryMixin
from .queue import (
    WorkflowLeaseLost,
    WorkflowRunAlreadyClaimed,
    WorkflowRunLease,
    WorkflowRunQueueRepositoryMixin,
)
from .state import WorkflowRunStateRepositoryMixin


class PostgresWorkflowRunRepository(
    WorkflowRunQueueRepositoryMixin,
    WorkflowRunStateRepositoryMixin,
    WorkflowRunHistoryRepositoryMixin,
    SyncPostgresRepository,
):
    """Compose queue, current-state, and history persistence capabilities."""

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        super().__init__(database_url)

    def _raw_connection(self) -> Any:
        return self.connection()

    def _advisory_lock_connection(self) -> Any:
        import psycopg2

        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://")
        return psycopg2.connect(raw_url)

    def is_connected(self) -> bool:
        try:
            connection = self.connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1;")
                return True
            finally:
                connection.close()
        except Exception:
            return False

    async def is_connected_async(self) -> bool:
        try:
            async with get_pooled_async_connection(self.database_url) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT 1;")
                    await cursor.fetchone()
            return True
        except Exception:
            return False


__all__ = [
    "WorkflowLeaseLost",
    "WorkflowRunAlreadyClaimed",
    "WorkflowRunLease",
    "PostgresWorkflowRunRepository",
]
