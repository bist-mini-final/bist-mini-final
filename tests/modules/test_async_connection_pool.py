from __future__ import annotations

import asyncio

from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import (
    close_async_pool,
    get_async_pool,
    get_pooled_async_connection,
)


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
