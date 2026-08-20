"""Singleton psycopg2 connection pool for PostgreSQL/pgvector access.

All DB operations in pgvector_store.py and db_manager.py should acquire
connections via :func:`get_connection` instead of opening a new TCP socket
on every call.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
import psycopg2.extensions
import psycopg2.pool

logger = logging.getLogger(__name__)

_MIN_CONN = 2
_MAX_CONN = 10

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


@contextmanager
def get_connection(
    database_url: str,
) -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager that borrows a connection from the pool and returns it
    on exit.

    * On exception: rolls back any open transaction, then returns to pool.
    * ``autocommit`` is reset to ``False`` before the connection is returned,
      so callers that set it (e.g. ``CREATE INDEX CONCURRENTLY``) do not
      pollute pooled connections.
    """
    pool = get_pool(database_url)
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        # Always restore default state before returning to pool.
        try:
            if conn.autocommit:
                conn.autocommit = False
        except Exception:
            pass
        pool.putconn(conn)


def close_pool() -> None:
    """Close all pooled connections.  Intended for clean server shutdown."""
    global _pool
    if _pool is not None:
        with _lock:
            if _pool is not None:
                try:
                    _pool.closeall()
                except Exception:
                    logger.warning("Connection pool close failed", exc_info=True)
                finally:
                    _pool = None
                    _pool_url = None
                    logger.info("psycopg2 connection pool closed")
