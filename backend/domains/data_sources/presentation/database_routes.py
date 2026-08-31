"""Database health and connection-check endpoints for data sources."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.domains.data_sources.application.ports import DataSourceDatabasePort

logger = logging.getLogger(__name__)

_ALLOWED_DB_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "postgres", "pgvector", "bist-pgvector"}
)
_POSTGRES_SCHEMES = frozenset({"postgresql", "postgresql+psycopg", "postgres"})


class DbConnectRequestDTO(BaseModel):
    """PostgreSQL + pgvector 데이터베이스 연결 테스트 요청 DTO."""

    database_url: str = Field(
        min_length=1,
        description="PostgreSQL + pgvector 접속 URL (예: postgresql://...)",
    )


def _allowed_database_endpoint(
    host: str | None,
    port: int | None,
    configured_database_url: str,
) -> bool:
    if not host:
        return False
    configured = urlparse(configured_database_url)
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
    database: DataSourceDatabasePort,
    configured_database_url: str,
) -> APIRouter:
    """PostgreSQL + pgvector 데이터베이스 헬스 및 연결 진단을 위한 FastAPI 라우터 생성."""
    router = APIRouter()

    @router.get(
        "/db-status",
        summary="PostgreSQL 및 pgvector 연결 상태 및 컬렉션 요약 조회",
        description="현재 바인딩된 PostgreSQL 데이터베이스의 pgvector 확장 활성화 여부, 전체 컬렉션 수, 총 벡터 청크 수를 반환합니다.",
    )
    def get_db_status() -> dict[str, Any]:
        """데이터베이스 연결 상태와 벡터 인덱스 총계를 반환합니다."""
        return database.current_info()

    @router.post(
        "/db-connect",
        summary="외부 PostgreSQL + pgvector 연결 테스트",
        description="입력받은 데이터베이스 URL로 직접 연결을 시도하여 접속 가능 여부 및 pgvector 확장을 검증합니다.",
    )
    def test_db_connect(request: DbConnectRequestDTO) -> dict[str, Any]:
        """지정된 데이터베이스 URL에 대한 연결 가능 여부를 진단합니다."""
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
        if not _allowed_database_endpoint(
            parsed.hostname,
            port,
            configured_database_url,
        ):
            raise HTTPException(
                status_code=400,
                detail="허용되지 않은 데이터베이스 호스트입니다.",
            )

        host = parsed.hostname or "localhost"
        resolved_port = port or 5432
        database_name = parsed.path.lstrip("/") or "rag_flow"
        try:
            info = database.inspect(request.database_url)
        except Exception as error:
            logger.warning("Database connection test failed: %s", error)
            return _failed_connection(host, resolved_port, database_name)
        return info if info.get("connected") else _failed_connection(
            host,
            resolved_port,
            database_name,
        )

    return router


__all__ = ["DbConnectRequestDTO", "create_database_router"]
