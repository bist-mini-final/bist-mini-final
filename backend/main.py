import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.api.router import create_api_router
from backend.features.bi.api_routes import register_bi_exception_handlers
from backend.core.settings import DEV_CORS_ORIGINS, DIST_DIR
from backend.storage.answer_cache import AnswerCacheRepository
from modules.common.exceptions import PipelineBaseError

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    repository = AnswerCacheRepository()

    application = FastAPI(
        title="RAG Pipeline Visualizer API",
        version="2.0.0",
        description=(
            "독립 실행 가능한 RAG·스프레드시트 모듈과 DTO 기반 워크플로 API입니다. "
            "각 모듈 실행 엔드포인트는 Input/Config/Output Pydantic 스키마를 "
            "Swagger에 직접 노출합니다."
        ),
        openapi_tags=[
            {
                "name": "Modules",
                "description": "모듈 계약 조회와 모듈별 독립 JSON 실행",
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
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_CORS_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    register_global_exception_handlers(application)
    application.include_router(create_api_router(repository))
    register_bi_exception_handlers(application)

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
        if reserved_prefix in {"api", "assets", "docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404, detail="Not Found")
        return frontend_index_response()

    return application


def register_global_exception_handlers(application: FastAPI) -> None:
    """Register centralized standard JSON exception handlers across all pipeline and server errors."""

    @application.exception_handler(PipelineBaseError)
    async def pipeline_exception_handler(request: Request, exc: PipelineBaseError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @application.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "데이터 유효성 검증에 실패했습니다.",
                "module_type": None,
                "details": {"errors": exc.errors(include_url=False)},
            },
        )

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": "HTTP_ERROR",
                "message": str(exc.detail),
                "module_type": None,
                "details": {"status_code": exc.status_code},
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled global server exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "서버 내부 오류가 발생했습니다.",
                "module_type": None,
                "details": {"error": str(exc)},
            },
        )


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8765, reload=True)
