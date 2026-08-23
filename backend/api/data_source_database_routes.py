"""Database health and connection-check endpoints for data sources."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.settings import PGVECTOR_URL
from backend.storage.pgvector_probe import PgVectorConnectionProbe
from backend.storage.pgvector_store import PgVectorStore

logger = logging.getLogger(__name__)

_ALLOWED_DB_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "postgres", "pgvector", "bist-pgvector"}
)
_POSTGRES_SCHEMES = frozenset({"postgresql", "postgresql+psycopg", "postgres"})


class DbConnectRequestDTO(BaseModel):
    database_url: str = Field(
        min_length=1,
        description="PostgreSQL + pgvector 접속 URL",
    )


def _allowed_database_endpoint(host: str | None, port: int | None) -> bool:
    if not host:
        return False
    configured = urlparse(PGVECTOR_URL)
    normalized = host.strip("[]").casefold()
    configured_host = (configured.hostname or "").strip("[]").casefold()
    if normalized not in _ALLOWED_DB_HOSTS and normalized != configured_host:
        return False
    allowed_ports = {5432, configured.port} - {None}
    return port is None or port in allowed_ports


def _failed_connection(host: str, port: int, database: str) -> dict[str, Any]:
    return {
        "connected": False,
        "host": host,
        "port": port,
        "database": database,
        "framework": "psycopg + pgvector",
        "error": "데이터베이스 연결에 실패했습니다.",
        "total_indexes": 0,
        "total_chunks": 0,
    }


def create_database_router(
    pgvector_store: PgVectorStore,
    connection_probe: PgVectorConnectionProbe,
) -> APIRouter:
    router = APIRouter()

    @router.get("/db-status")
    def get_db_status() -> dict[str, Any]:
        return pgvector_store.get_db_info()

    @router.post("/db-connect")
    def test_db_connect(request: DbConnectRequestDTO) -> dict[str, Any]:
        try:
            parsed = urlparse(request.database_url)
            port = parsed.port
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 데이터베이스 URL입니다.",
            ) from error

        if parsed.scheme.casefold() not in _POSTGRES_SCHEMES:
            raise HTTPException(
                status_code=400,
                detail="PostgreSQL 데이터베이스 URL만 지원됩니다.",
            )
        if not _allowed_database_endpoint(parsed.hostname, port):
            raise HTTPException(
                status_code=400,
                detail="허용되지 않은 데이터베이스 호스트입니다.",
            )

        host = parsed.hostname or "localhost"
        resolved_port = port or 5432
        database = parsed.path.lstrip("/") or "rag_flow"
        try:
            info = connection_probe.inspect(request.database_url)
        except Exception as error:
            logger.warning("Database connection test failed: %s", error)
            return _failed_connection(host, resolved_port, database)
        return info if info.get("connected") else _failed_connection(
            host,
            resolved_port,
            database,
        )

    return router


__all__ = ["DbConnectRequestDTO", "create_database_router"]
