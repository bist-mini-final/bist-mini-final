from __future__ import annotations

import asyncio
from uuid import uuid4

from backend.core.settings import PGVECTOR_URL
from backend.platform.postgres.pool import (
    close_async_pool,
    get_async_pool,
    get_pooled_async_connection,
)
from backend.storage.db_manager import DatabaseManager


def test_async_connection_pool_is_reused_and_executes_without_thread_adapter() -> None:
    async def scenario() -> None:
        first = await get_async_pool(PGVECTOR_URL)
        second = await get_async_pool(PGVECTOR_URL)
        assert first is second
        async with get_pooled_async_connection(PGVECTOR_URL) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
                assert await cursor.fetchone() == (1,)
        await close_async_pool(PGVECTOR_URL)

    asyncio.run(scenario())


def test_database_manager_persists_source_metadata_with_async_pool() -> None:
    async def scenario() -> None:
        file_id = uuid4().hex
        manager = DatabaseManager(PGVECTOR_URL, ensure_schema=False)
        assert await manager.is_connected_async()
        await manager.save_source_file_async(
            file_id=file_id,
            file_name="async-upload.xlsx",
            file_hash=file_id,
            file_type="xlsx",
            file_size=123,
            storage_path="C:/tmp/async-upload.xlsx",
        )
        async with get_pooled_async_connection(PGVECTOR_URL) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT file_name, file_size FROM source_files WHERE file_id = %s",
                    (file_id,),
                )
                assert await cursor.fetchone() == ("async-upload.xlsx", 123)
                await cursor.execute(
                    "DELETE FROM source_files WHERE file_id = %s",
                    (file_id,),
                )
            await connection.commit()
        await close_async_pool(PGVECTOR_URL)

    asyncio.run(scenario())
