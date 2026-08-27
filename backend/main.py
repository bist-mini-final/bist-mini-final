"""FastAPI application factory and process entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.exception_handlers import register_global_exception_handlers
from backend.api.middleware import RequestObservabilityMiddleware
from backend.api.openapi import OPENAPI_TAGS, custom_openapi_schema
from backend.api.router import create_api_router
from backend.api.spa import register_spa
from backend.api.system_routes import create_system_router
from backend.api.versioning import API_V1_PREFIX, API_VERSION, LEGACY_API_PREFIX
from backend.bootstrap.container import ApplicationContainer
from backend.bootstrap.lifecycle import create_lifespan
from backend.core.settings import DEV_CORS_ORIGINS
from backend.features.bi.api_routes import register_bi_exception_handlers


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    """Compose the HTTP application around one explicit service container."""

    shared_container = container or ApplicationContainer.create()
    application = FastAPI(
        title="BIST 엔터프라이즈 RAG 파이프라인 & BI 엔진 API",
        version=API_VERSION,
        description="RAG·스프레드시트 모듈 계약과 Kubernetes 기반 비동기 워크플로 API",
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=create_lifespan(shared_container),
    )
    application.state.container = shared_container
    application.openapi = lambda: custom_openapi_schema(application, shared_container)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_CORS_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestObservabilityMiddleware)
    register_global_exception_handlers(application)
    register_bi_exception_handlers(application)

    application.include_router(create_system_router())
    api_router = create_api_router(shared_container)
    application.include_router(api_router, prefix=API_V1_PREFIX)
    application.include_router(
        api_router,
        prefix=LEGACY_API_PREFIX,
        include_in_schema=False,
    )
    register_spa(application)
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8765, reload=True)


__all__ = ["app", "create_app", "register_global_exception_handlers"]
