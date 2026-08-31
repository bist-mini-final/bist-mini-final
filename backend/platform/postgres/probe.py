"""PostgreSQL connectivity probe used by composition and health endpoints."""

from __future__ import annotations

from backend.core.settings import PGVECTOR_URL

from .pool import get_pooled_async_connection, get_pooled_raw_connection


class PostgresConnectionProbe:
    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self.database_url = database_url

    def is_connected(self) -> bool:
        try:
            connection = get_pooled_raw_connection(self.database_url)
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


__all__ = ["PostgresConnectionProbe"]
