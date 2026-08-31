"""Compatibility imports for :mod:`backend.platform.postgres.pool`."""

from backend.platform.postgres.pool import (
    AsyncConnectionPoolRegistry,
    ConnectionPoolRegistry,
    PooledConnectionWrapper,
    close_async_pool,
    close_pool,
    get_async_pool,
    get_pool,
    get_pooled_async_connection,
    get_pooled_raw_connection,
)

__all__ = [
    "AsyncConnectionPoolRegistry",
    "ConnectionPoolRegistry",
    "PooledConnectionWrapper",
    "close_async_pool",
    "close_pool",
    "get_async_pool",
    "get_pool",
    "get_pooled_async_connection",
    "get_pooled_raw_connection",
]
