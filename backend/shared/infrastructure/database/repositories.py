"""Small PostgreSQL adapter bases shared by domain repositories.

These classes own connection acquisition only. Domain repositories retain
their own queries and transaction boundaries instead of inheriting a generic
CRUD API that would erase domain intent.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator, Protocol, runtime_checkable

from backend.storage.connection_pool import (
    get_pooled_async_connection,
    get_pooled_raw_connection,
)


@runtime_checkable
class DatabaseUrlProvider(Protocol):
    """Minimal connection configuration exposed across composition roots."""

    @property
    def database_url(self) -> str: ...


def _database_url(source: str | DatabaseUrlProvider) -> str:
    return source if isinstance(source, str) else source.database_url


class SyncPostgresRepository:
    """Base for synchronous repositories executed by worker processes."""

    def __init__(self, database: str | DatabaseUrlProvider) -> None:
        self._database_url = _database_url(database)

    @property
    def database_url(self) -> str:
        return self._database_url

    def connection(self) -> Any:
        """Borrow a pooled connection; callers must close or context-manage it."""

        return get_pooled_raw_connection(self._database_url)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Commit on success and roll back before returning a failed session."""

        with self.connection() as connection:
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise


class AsyncPostgresRepository:
    """Base for event-loop-native repositories used on HTTP hot paths."""

    def __init__(self, database: str | DatabaseUrlProvider) -> None:
        self._database_url = _database_url(database)

    @property
    def database_url(self) -> str:
        return self._database_url

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Any]:
        async with get_pooled_async_connection(self._database_url) as connection:
            yield connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        async with self.connection() as connection:
            async with connection.transaction():
                yield connection


__all__ = [
    "AsyncPostgresRepository",
    "DatabaseUrlProvider",
    "SyncPostgresRepository",
]
