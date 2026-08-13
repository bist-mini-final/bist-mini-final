"""FastAPI entry point for the RAG Pipeline Visualizer."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.answer_cache import AnswerCacheRepository
from backend.config import CACHE_DIR, DEV_CORS_ORIGINS, DIST_DIR
from backend.routes import create_api_router

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

    @application.get("/")
    def serve_index():
        index_path = DIST_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse(
            "<h1>Frontend build not found</h1><p>Run the frontend build first.</p>",
            status_code=404,
        )

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8765, reload=True)
