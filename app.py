"""FastAPI entry point for the RAG Pipeline Visualizer."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.router import create_api_router
from backend.core.settings import CACHE_DIR, DEV_CORS_ORIGINS, DIST_DIR
from backend.storage.answer_cache import AnswerCacheRepository

def create_app() -> FastAPI:
    repository = AnswerCacheRepository(CACHE_DIR / "answers.json")

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
    application.include_router(create_api_router(repository))

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


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8765, reload=True)
