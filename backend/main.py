"""Main FastAPI application entry point with lifespan management, health probes, centralized error handling, and hierarchical ReDoc documentation."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, AsyncGenerator, Dict

from anyio import to_thread
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
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
# 4. Custom OpenAPI with ReDoc Hierarchical x-tagGroups & External Modules Schema
# ==============================================================================
def custom_openapi_schema(app: FastAPI) -> Dict[str, Any]:
    """x-tagGroups 계층 구조와 전체 외부 파이프라인 모듈의 Pydantic DTO 스키마를 포함하는 OpenAPI 스키마 생성."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="BIST 엔터프라이즈 RAG 파이프라인 & BI 엔진 API",
        version="2.0.0",
        description=(
            "### 🏢 BIST Mini Final — 엔터프라이즈 RAG 파이프라인 및 BI 엔진\n\n"
            "재무 스프레드시트 구조 분석, **Luna VLM 비정형 표 감지**, **PostgreSQL/pgvector 하이브리드 검색 (Dense + FTS + RRF)**, "
            "근거 기반 수식 답변 생성, **BI 대시보드 지표 추출** 및 **RAG 파이프라인 벤치마크 평가**를 위한 엔터프라이즈 REST API 명세서입니다.\n\n"
            "#### 📂 아키텍처 계층 및 시스템 구성\n"
            "- **`modules/`**: 19개 RAG 파이프라인 모듈 및 Pydantic v2 계약의 단일 소스 (Single Source of Truth)\n"
            "- **`jobs/`**: 선언적 DAG 파이프라인 레시피 및 전용 배치 워커 엔트리포인트\n"
            "- **FastAPI Control Plane**: API 계약 검증, PostgreSQL 큐 등록, 스냅샷 영속화, SSE 실시간 스트리밍 제공\n"
            "- **KEDA ScaledJobs**: 4개 독립 큐(`workflow-core`, `bi-materialization`, `bi-question`, `benchmark`) 기반 쿠버네티스 수평 자동 확장\n"
        ),
        routes=app.routes,
    )

    # 1. ReDoc 계층형 사이드바 x-tagGroups 정의 (완전 한글화)
    openapi_schema["x-tagGroups"] = [
        {
            "name": "1. 시스템 및 인프라",
            "tags": ["시스템 헬스 & 프로브", "데이터 소스 관리", "스프레드시트 렌더 아티팩트"],
        },
        {
            "name": "2. RAG 파이프라인 모듈",
            "tags": ["모듈 카탈로그 및 스키마"],
        },
        {
            "name": "3. DAG 워크플로 엔진",
            "tags": ["워크플로 정의 관리", "워크플로 실행 및 실시간 스트림"],
        },
        {
            "name": "4. BI 대시보드 및 분석 엔진",
            "tags": [
                "BI 기업 목록 및 개요",
                "BI 대시보드 스냅샷",
                "BI 머티리얼라이제이션 작업",
                "BI 지표 질문 및 배치 계산",
            ],
        },
        {
            "name": "5. RAG 벤치마크 평가",
            "tags": ["벤치마크 실행 및 채점"],
        },
    ]

    # 2. Inject External modules/* Pydantic DTO Schemas into components/schemas
    container: ApplicationContainer | None = getattr(app.state, "container", None)
    if container is not None:
        schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
        try:
            modules = container.runtime.services.module_registry.list_modules()
            for module in modules:
                for model_attr in ("input_model", "config_model", "output_model"):
                    model_cls = getattr(module, model_attr, None)
                    if model_cls is not None and hasattr(model_cls, "model_json_schema"):
                        try:
                            schema_dict = model_cls.model_json_schema(
                                mode="serialization",
                                ref_template="#/components/schemas/{model}",
                            )
                            schema_name = model_cls.__name__
                            if schema_name not in schemas:
                                schemas[schema_name] = schema_dict
                            # In case model_json_schema generated $defs, merge them into schemas
                            defs = schema_dict.pop("$defs", {})
                            for def_name, def_schema in defs.items():
                                if def_name not in schemas:
                                    schemas[def_name] = def_schema
                        except Exception as exc:
                            logger.debug("Failed to extract schema for %s: %s", model_cls, exc)
        except Exception as exc:
            logger.warning("Failed to auto-inject modules schemas into OpenAPI: %s", exc)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


# ==============================================================================
# 5. Application Factory
# ==============================================================================
def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    shared_container = container or ApplicationContainer.create()
    application = FastAPI(
        title="BIST 엔터프라이즈 RAG 파이프라인 & BI 엔진 API",
        version="2.0.0",
        description="RAG·스프레드시트 모듈 계약과 Kubernetes 기반 비동기 워크플로 API",
        openapi_tags=[
            {
                "name": "시스템 헬스 & 프로브",
                "description": "쿠버네티스 Liveness/Readiness 프로브 및 백엔드 서비스 상태 진단 엔드포인트",
            },
            {
                "name": "데이터 소스 관리",
                "description": "재무제표 엑셀 파일 업로드, 다운로드, 시트 미리보기, 데이터베이스 연결 테스트 및 pgvector 인덱스 컬렉션 관리",
            },
            {
                "name": "스프레드시트 렌더 아티팩트",
                "description": "Luna VLM 시각 구조 감지 엔진이 생성한 고해상도 시트 렌더링(rendered) 및 셀 타입 마스킹(typed) PNG 이미지 서빙",
            },
            {
                "name": "모듈 카탈로그 및 스키마",
                "description": "`modules/` 디렉토리에 위치한 19개 RAG 파이프라인 모듈의 포트 계약, 입출력 정의 및 Pydantic DTO 스키마 조회",
            },
            {
                "name": "워크플로 정의 관리",
                "description": "XYFlow 기반 DAG 파이프라인 노드와 엣지 토폴로지 정의의 생성, 조회, 수정 및 삭제",
            },
            {
                "name": "워크플로 실행 및 실시간 스트림",
                "description": "PostgreSQL 큐 및 KEDA 기반 비동기 DAG 워크플로 실행, 재개, 취소 및 Server-Sent Events 실시간 실행 텔레메트리 스트리밍",
            },
            {
                "name": "BI 기업 목록 및 개요",
                "description": "인덱싱된 기업 목록, 바인딩된 원본 스프레드시트 정보 및 최신 BI 대시보드 머티리얼라이제이션 상태 요약",
            },
            {
                "name": "BI 대시보드 스냅샷",
                "description": "기업별 18개 재무 지표 시계열, 공식 계산 결과, 출처 셀 링크 및 데이터 검증 이슈가 포함된 완성형 BI 대시보드 스냅샷",
            },
            {
                "name": "BI 머티리얼라이제이션 작업",
                "description": "스프레드시트 구조 프로파일링 및 지표 질문 생성 머티리얼라이제이션 백그라운드 작업 관리 및 진행 상태 스트리밍",
            },
            {
                "name": "BI 지표 질문 및 배치 계산",
                "description": "OpenAI Responses LLM을 통한 병렬 재무 지표 추출 질문 배치 실행, 재계산 요청 및 실시간 진행률 구독",
            },
            {
                "name": "벤치마크 실행 및 채점",
                "description": "사전 정의된 골든 데이터셋 기반 RAG 파이프라인 정확도, LLM 비용, 응답 지연 시간 평가 및 채점 결과 조회",
            },
        ],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.container = shared_container

    # Override openapi schema generator
    application.openapi = lambda: custom_openapi_schema(application)

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
    @application.get(
        "/healthz",
        tags=["시스템 헬스 & 프로브"],
        summary="전체 시스템 헬스 상태 확인",
        description="백엔드 서비스 활성화 여부, 버전, 타임스탬프를 반환합니다.",
    )
    def health_check() -> dict:
        """시스템 헬스 상태와 버전 정보를 반환합니다."""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "service": "bist-rag-backend",
            "version": "2.0.0",
        }

    @application.get(
        "/livez",
        tags=["시스템 헬스 & 프로브"],
        summary="Kubernetes Liveness Probe",
        description="Pod가 정상 실행 중인지 확인하는 쿠버네티스 라이브니스 프로브입니다.",
    )
    def liveness_probe() -> dict:
        """쿠버네티스 라이브니스 프로브 응답을 반환합니다."""
        return {"status": "alive"}

    @application.get(
        "/readyz",
        tags=["시스템 헬스 & 프로브"],
        summary="Kubernetes Readiness Probe",
        description="PostgreSQL DB 커넥션 풀 연결 상태를 검증하는 쿠버네티스 레디니스 프로브입니다.",
    )
    def readiness_probe() -> JSONResponse:
        """쿠버네티스 레디니스 프로브로 PostgreSQL 연결 상태를 점검합니다."""
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
        """Serve the frontend single-page application index."""
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
