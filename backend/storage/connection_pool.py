"""Singleton psycopg2 connection pool for PostgreSQL/pgvector access."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

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
_MAX_CONN = max(_MIN_CONN, _pool_size("DB_POOL_MAX_SIZE", 10))

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_url: Optional[str] = None
_lock = threading.Lock()


def _normalize_url(database_url: str) -> str:
    """Strip SQLAlchemy dialect prefix so psycopg2 can parse the URL."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


def get_pool(database_url: str) -> psycopg2.pool.ThreadedConnectionPool:
    """Return the process-wide connection pool, creating it on first call.

    The pool is re-created automatically when *database_url* changes
    (e.g. during tests that swap DB URLs).
    """
    global _pool, _pool_url
    normalized = _normalize_url(database_url)
    if _pool is None or _pool_url != normalized:
        with _lock:
            if _pool is None or _pool_url != normalized:
                if _pool is not None:
                    try:
                        _pool.closeall()
                    except Exception:
                        pass
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    _MIN_CONN,
                    _MAX_CONN,
                    normalized,
                    connect_timeout=10,
                )
                _pool_url = normalized
                logger.info(
                    "psycopg2 connection pool initialised (min=%d, max=%d)",
                    _MIN_CONN,
                    _MAX_CONN,
                )
    return _pool


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


def get_pooled_raw_connection(database_url: str) -> PooledConnectionWrapper:
    """Borrow a connection from the process-wide pool and wrap it so .close() returns it to pool."""
    pool = get_pool(database_url)
    # psycopg2's ThreadedConnectionPool.getconn accepts only an optional key;
    # connection timeouts belong to pool construction/connect_timeout.
    conn = pool.getconn()
    return PooledConnectionWrapper(pool, conn)
