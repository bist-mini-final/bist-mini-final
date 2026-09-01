"""Compose the FastAPI control plane from domain routers and application services."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import (
    AuthenticationMiddleware,
    AuthSettings,
    SessionAuthenticator,
)
from backend.api.exception_handlers import register_global_exception_handlers
from backend.api.middleware import (
    RequestObservabilityMiddleware,
    SecurityHeadersMiddleware,
)
from backend.api.openapi import OPENAPI_TAGS, custom_openapi_schema
from backend.api.router import create_api_router
from backend.api.spa import register_spa
from backend.api.system_routes import create_system_router
from backend.api.versioning import API_V1_PREFIX, API_VERSION, LEGACY_API_PREFIX
from backend.bootstrap.application import ApplicationContainer
from backend.bootstrap.lifecycle import create_lifespan
from backend.core.settings import DEV_CORS_ORIGINS, EXPOSE_API_DOCS, REDIS_URL
from backend.domains.bi.presentation.routes import register_bi_exception_handlers
from backend.platform.redis.state_stream_broker import create_state_stream_broker


def create_app(
    container: ApplicationContainer | None = None,
    *,
    expose_api_docs: bool | None = None,
    auth_settings: AuthSettings | None = None,
) -> FastAPI:
    """Compose the HTTP application around one explicit service container."""

    shared_container = container or ApplicationContainer.create()
    state_stream_broker = create_state_stream_broker(REDIS_URL)
    docs_enabled = EXPOSE_API_DOCS if expose_api_docs is None else expose_api_docs
    authenticator = SessionAuthenticator(
        auth_settings if auth_settings is not None else AuthSettings.from_environment()
    )
    application = FastAPI(
        title="BIST 엔터프라이즈 RAG 파이프라인 & BI 엔진 API",
        version=API_VERSION,
        description="RAG·스프레드시트 모듈 계약과 Kubernetes 기반 비동기 워크플로 API",
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=create_lifespan(
            shared_container,
            on_shutdown=(state_stream_broker.aclose if state_stream_broker else None),
        ),
    )
    application.openapi = lambda: custom_openapi_schema(application, shared_container)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_CORS_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestObservabilityMiddleware)
    application.add_middleware(
        AuthenticationMiddleware,
        authenticator=authenticator,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    register_global_exception_handlers(application)
    register_bi_exception_handlers(application)

    application.include_router(
        create_system_router(shared_container.runtime.services.database_probe.is_connected_async)
    )
    api_router = create_api_router(
        shared_container,
        authenticator=authenticator,
        state_stream_broker=state_stream_broker,
    )
    application.include_router(api_router, prefix=API_V1_PREFIX)
    application.include_router(
        api_router,
        prefix=LEGACY_API_PREFIX,
        include_in_schema=False,
    )
    register_spa(application)
    return application


__all__ = ["create_app", "register_global_exception_handlers"]
