"""Root-level health and Kubernetes probe routes."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from backend.api.versioning import API_VERSION


def create_system_router(
    is_database_connected: Callable[[], Awaitable[bool]],
) -> APIRouter:
    router = APIRouter(tags=["시스템 헬스 & 프로브"])

    @router.get("/healthz", summary="전체 시스템 헬스 상태 확인")
    def health_check() -> dict[str, str | float]:
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "service": "bist-rag-backend",
            "version": API_VERSION,
        }

    @router.get("/livez", summary="Kubernetes Liveness Probe")
    def liveness_probe() -> dict[str, str]:
        return {"status": "alive"}

    @router.get("/readyz", summary="Kubernetes Readiness Probe")
    async def readiness_probe() -> JSONResponse:
        try:
            connected = await is_database_connected()
        except Exception as error:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": str(error)},
            )
        if not connected:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": "disconnected"},
            )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "database": "connected"},
        )

    return router


__all__ = ["create_system_router"]
