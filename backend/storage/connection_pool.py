"""Process-owned psycopg2 connection pools keyed by PostgreSQL URL."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import psycopg2
import psycopg2.extensions
import psycopg2.pool

logger = logging.getLogger(__name__)


def _pool_size(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        logger.warning("%s 값이 정수가 아니어서 기본값 %d을 사용합니다", name, default)
        return default


_MIN_CONN = _pool_size("DB_POOL_MIN_SIZE", 2)
_MAX_CONN = max(_MIN_CONN, _pool_size("DB_POOL_MAX_SIZE", 50))

def _normalize_url(database_url: str) -> str:
    """Strip SQLAlchemy dialect prefix so psycopg2 can parse the URL."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


class ConnectionPoolRegistry:
    """Own one reusable pool per normalized database URL.

    A connection test against a second database must not close the production
    pool while requests are using it. Pool ownership therefore belongs to this
    registry rather than to whichever caller most recently requested a URL.
    """

    def __init__(self) -> None:
        self._pools: dict[str, psycopg2.pool.ThreadedConnectionPool] = {}
        self._lock = threading.Lock()

    def get(self, database_url: str) -> psycopg2.pool.ThreadedConnectionPool:
        normalized = _normalize_url(database_url)
        existing = self._pools.get(normalized)
        if existing is not None:
            return existing

        with self._lock:
            existing = self._pools.get(normalized)
            if existing is not None:
                return existing
            created = psycopg2.pool.ThreadedConnectionPool(
                _MIN_CONN,
                _MAX_CONN,
                normalized,
                connect_timeout=10,
                options=(
                    "-c hnsw.iterative_scan=strict_order "
                    "-c hnsw.max_scan_tuples=20000 "
                    "-c hnsw.ef_search=40"
                ),
            )
            self._pools[normalized] = created
            logger.info(
                "psycopg2 connection pool initialised (min=%d, max=%d)",
                _MIN_CONN,
                _MAX_CONN,
            )
            return created

    def close(self, database_url: str | None = None) -> None:
        """Close one URL pool, or every owned pool when no URL is supplied."""
        with self._lock:
            if database_url is None:
                pools = list(self._pools.values())
                self._pools.clear()
            else:
                pool = self._pools.pop(_normalize_url(database_url), None)
                pools = [pool] if pool is not None else []
        for pool in pools:
            try:
                pool.closeall()
            except Exception as error:
                logger.warning("Error closing connection pool: %s", error)


_POOL_REGISTRY = ConnectionPoolRegistry()


def get_pool(database_url: str) -> psycopg2.pool.ThreadedConnectionPool:
    """Return the stable process pool associated with ``database_url``."""
    return _POOL_REGISTRY.get(database_url)


class PooledConnectionWrapper:
    """Wraps a psycopg2 connection checked out from ThreadedConnectionPool.

    Calling .close() returns the connection back to the pool instead of destroying
    the underlying TCP socket.
    """

    def __init__(
        self,
        pool: psycopg2.pool.ThreadedConnectionPool,
        conn: psycopg2.extensions.connection,
    ) -> None:
        self._pool = pool
        self._conn = conn
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        try:
            try:
                if (
                    self._conn.get_transaction_status()
                    != psycopg2.extensions.TRANSACTION_STATUS_IDLE
                ):
                    self._conn.rollback()
            except Exception as error:
                logger.error(
                    "커넥션 트랜잭션 복구 실패로 풀에 반환하지 않고 직접 닫습니다: %s",
                    error,
                )
                try:
                    self._conn.close()
                except Exception:
                    pass
                return
            try:
                if getattr(self._conn, "autocommit", False):
                    self._conn.autocommit = False
            except Exception as error:
                logger.error(
                    "커넥션 autocommit 복구 실패로 커넥션을 풀에 반환하지 않고 직접 닫습니다: %s",
                    error,
                )
                try:
                    self._conn.close()
                except Exception:
                    pass
                return

            try:
                self._pool.putconn(self._conn)
            except Exception as error:
                logger.error(
                    "커넥션 풀 반환(putconn) 실패로 커넥션을 직접 닫습니다: %s",
                    error,
                )
                try:
                    self._conn.close()
                except Exception:
                    pass
        finally:
            self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("_pool", "_conn", "_closed"):
            super().__setattr__(name, value)
        else:
            setattr(self._conn, name, value)

    def __enter__(self) -> "PooledConnectionWrapper":
        return self

    def __exit__(self, exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        if exc_type is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass
        self.close()


def get_pooled_raw_connection(database_url: str, timeout_seconds: float = 15.0) -> PooledConnectionWrapper:
    """Borrow a connection from the process-wide pool and wrap it so .close() returns it to pool.
    
    If the pool is temporarily exhausted, waits up to timeout_seconds with exponential/short backoff.
    """
    pool = get_pool(database_url)
    deadline = time.time() + timeout_seconds
    while True:
        try:
            conn = pool.getconn()
            return PooledConnectionWrapper(pool, conn)
        except psycopg2.pool.PoolError:
            if time.time() >= deadline:
                raise
            time.sleep(0.02)


def close_pool(database_url: str | None = None) -> None:
    """Close one registered pool, or all process-owned pools."""
    _POOL_REGISTRY.close(database_url)
