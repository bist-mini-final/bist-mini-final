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

    application = FastAPI(title="RAG Pipeline Visualizer", version="1.1.0")
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
