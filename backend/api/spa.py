"""Production SPA static asset registration and history fallback."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.core.settings import DIST_DIR

_RESERVED_PREFIXES = {
    "api",
    "assets",
    "docs",
    "redoc",
    "openapi.json",
    "healthz",
    "livez",
    "readyz",
}


def register_spa(application: FastAPI) -> None:
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    def frontend_index_response() -> Response:
        index_path = DIST_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        return JSONResponse(
            status_code=503,
            content={"detail": "Frontend assets are not available."},
        )

    @application.get("/", include_in_schema=False)
    def serve_index() -> Response:
        return frontend_index_response()

    @application.get("/{frontend_path:path}", include_in_schema=False)
    def serve_frontend_route(frontend_path: str) -> Response:
        if frontend_path.partition("/")[0] in _RESERVED_PREFIXES:
            raise HTTPException(status_code=404, detail="Not Found")
        return frontend_index_response()


__all__ = ["register_spa"]
