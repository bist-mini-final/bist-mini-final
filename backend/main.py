"""Main FastAPI application entry point with lifespan management, health probes, and centralized error handling."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from typing import AsyncGenerator
from zoneinfo import ZoneInfo

from anyio import to_thread
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.api.error_mapping import error_envelope, http_error_envelope
from backend.api.router import create_api_router
from backend.bootstrap.container import ApplicationContainer
from backend.core.settings import (
    DATABASE_URL,
    DEV_CORS_ORIGINS,
    DIST_DIR,
    PROJECT_DIR,
)
from backend.features.bi.api_routes import register_bi_exception_handlers
from backend.storage.connection_pool import close_pool, get_pool
from modules.common.exceptions import PipelineBaseError

logger = logging.getLogger("backend.main")


# ==============================================================================
# 1. Lifespan Management (Startup & Shutdown Lifecycle)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: initialize resources on startup and clean up on shutdown."""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("🚀 Starting RAG Pipeline Visualizer Backend Engine...")
    logger.info("=" * 60)

    # 1. Ensure runtime directories exist
    (PROJECT_DIR / "data").mkdir(parents=True, exist_ok=True)

    # 2. Warm up Database Connection Pool
    try:
        pool = get_pool(DATABASE_URL)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
            logger.info("✅ Database connection pool verified successfully.")
        finally:
            pool.putconn(conn)
    except Exception as exc:
        logger.warning(
            "⚠️ Database initial connection check failed (will retry on demand): %s",
            exc,
        )

    container: ApplicationContainer = app.state.container
    available_modules = container.runtime.services.module_registry.list_modules()
    logger.info(
        "📦 Registered %d pipeline modules: %s",
        len(available_modules),
        ", ".join(module.definition.type for module in available_modules[:6])
        + ("..." if len(available_modules) > 6 else ""),
    )
    try:
        recovered = await to_thread.run_sync(container.recover_pending_runs)
        if recovered:
            logger.info("미완료 Kubernetes run %d개를 큐에 복구했습니다", recovered)
    except Exception:
        logger.warning("Kubernetes run 큐 복구 실패", exc_info=True)

    async def refresh_daily_suggestions() -> None:
        while True:
            try:
                await to_thread.run_sync(container.chat_suggestions.refresh_if_due)
            except Exception:
                logger.warning("일일 챗봇 추천 질문 갱신 실패", exc_info=True)
            now = datetime.now(ZoneInfo("Asia/Seoul"))
            next_run = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
            await asyncio.sleep((next_run - now).total_seconds())

    try:
        # 서버를 재시작하면 운영자가 즉시 새 추천 질문 세트를 확인할 수 있게 합니다.
        await to_thread.run_sync(lambda: container.chat_suggestions.refresh_if_due(force=True))
    except Exception:
        logger.warning("시작 시 챗봇 추천 질문 생성 실패", exc_info=True)
    suggestions_task = asyncio.create_task(refresh_daily_suggestions())

    elapsed = time.time() - start_time
    logger.info("✨ Application initialization complete in %.3fs.", elapsed)

    yield  # Application serves requests

    # Shutdown sequence
    logger.info("🛑 Shutting down backend application...")
    try:
        suggestions_task.cancel()
        with suppress(asyncio.CancelledError):
            await suggestions_task
        container.close()
        close_pool()
        logger.info("🔌 Database connection pools closed cleanly.")
    except Exception as exc:
        logger.error("❌ Error closing connection pool: %s", exc)

    logger.info("👋 Backend shutdown complete.")


# ==============================================================================
# 2. Performance & Request Timing Middleware
# ==============================================================================
class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Adds request ID, measures request duration, and attaches telemetry headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.time()

        response = await call_next(request)

        process_time_ms = (time.time() - start_time) * 1000.0
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"

        # Log slow requests (> 1000ms) for observability
        if process_time_ms > 1000.0 and request.url.path.startswith("/api/"):
            logger.warning(
                "⚠️ Slow Request: %s %s [%s] took %.2fms",
                request.method,
                request.url.path,
                response.status_code,
                process_time_ms,
            )

        return response


# ==============================================================================
# 3. Centralized Global Exception Handlers
# ==============================================================================
def register_global_exception_handlers(application: FastAPI) -> None:
    """Register centralized standard JSON exception handlers across all pipeline and server errors."""

    @application.exception_handler(PipelineBaseError)
    async def pipeline_exception_handler(request: Request, exc: PipelineBaseError) -> JSONResponse:
        payload = exc.to_dict()
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(
                code=str(payload["error_code"]),
                message=str(payload["message"]),
                retryable=exc.status_code >= 500,
                context={
                    "module_type": payload.get("module_type"),
                    **(payload.get("details") or {}),
                },
            ),
        )

    @application.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                code="VALIDATION_ERROR",
                message="데이터 유효성 검증에 실패했습니다.",
                context={"errors": exc.errors(include_url=False)},
            ),
        )

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=http_error_envelope(exc.detail, exc.status_code),
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled global server exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                code="INTERNAL_SERVER_ERROR",
                message="서버 내부 오류가 발생했습니다.",
                retryable=True,
            ),
        )


# ==============================================================================
# 4. Application Factory
# ==============================================================================
def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    shared_container = container or ApplicationContainer.create()
    application = FastAPI(
        title="RAG Pipeline Visualizer API",
        version="2.0.0",
        description=(
            "RAG·스프레드시트 모듈 계약과 Kubernetes 기반 비동기 워크플로 "
            "API입니다. Input/Config/Output Pydantic 스키마와 실행 상태를 "
            "Swagger에 노출합니다."
        ),
        openapi_tags=[
            {
                "name": "Health",
                "description": "쿠버네티스 프로브 및 시스템 상태 진단",
            },
            {
                "name": "Modules",
                "description": "워크플로 구성에 사용하는 모듈 계약 조회",
            },
            {
                "name": "Workflows",
                "description": "DTO 포트를 조합한 DAG 저장과 실행",
            },
            {
                "name": "Spreadsheet Artifacts",
                "description": "스프레드시트 분석 결과 이미지 조회",
            },
        ],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.container = shared_container

    # 1. Middlewares
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_CORS_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestObservabilityMiddleware)

    # 2. Global Exception Handlers
    register_global_exception_handlers(application)
    register_bi_exception_handlers(application)

    # 3. Health Check & Kubernetes Probes
    @application.get("/healthz", tags=["Health"], summary="System Health Status")
    def health_check() -> dict:
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "service": "bist-rag-backend",
            "version": "2.0.0",
        }

    @application.get("/livez", tags=["Health"], summary="Kubernetes Liveness Probe")
    def liveness_probe() -> dict:
        return {"status": "alive"}

    @application.get("/readyz", tags=["Health"], summary="Kubernetes Readiness Probe")
    def readiness_probe() -> JSONResponse:
        try:
            pool = get_pool(DATABASE_URL)
            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            finally:
                pool.putconn(conn)
            return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready", "database": "connected"})
        except Exception as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": str(exc)},
            )

    # 4. API Routers
    application.include_router(create_api_router(shared_container))

    # 5. Static Assets & SPA Fallback
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        application.mount(
            "/assets", StaticFiles(directory=assets_dir), name="assets"
        )

    def frontend_index_response():
        index_path = DIST_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        return RedirectResponse(url="/redoc")

    @application.get("/", include_in_schema=False)
    def serve_index():
        return frontend_index_response()

    @application.get("/{frontend_path:path}", include_in_schema=False)
    def serve_frontend_route(frontend_path: str):
        """Return the SPA entry point for direct navigation to frontend routes."""
        reserved_prefix = frontend_path.partition("/")[0]
        if reserved_prefix in {"api", "assets", "docs", "redoc", "openapi.json", "healthz", "livez", "readyz"}:
            raise HTTPException(status_code=404, detail="Not Found")
        return frontend_index_response()

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8765, reload=True)
