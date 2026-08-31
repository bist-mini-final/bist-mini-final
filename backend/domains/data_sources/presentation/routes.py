"""Composition and HTTP route declarations for Data Sources."""

from __future__ import annotations

from fastapi import APIRouter

from backend.domains.data_sources.application.services import DataSourceApiServices

from .controller import (
    DataSourceHttpController,
    SearchRequestDTO,
    UpdateIndexCompanyRequestDTO,
)
from .database_routes import create_database_router
from .file_routes import create_data_source_file_router
from .index_routes import create_data_source_index_router
from .ingestion_routes import create_ingestion_router


def create_data_source_router(
    services: DataSourceApiServices,
) -> APIRouter:
    """Declare Data Sources endpoints over focused presentation controllers."""
    router = APIRouter(prefix="/data-sources", tags=["데이터 소스 관리"])
    controller = DataSourceHttpController(
        processed_dir=services.processed_dir,
        file_storage=services.file_storage,
        file_service=services.files,
        catalog=services.catalog,
    )
    router.include_router(
        create_database_router(
            services.database,
            services.configured_database_url,
        )
    )
    router.include_router(
        create_ingestion_router(
            services.ingestion,
            services.runs,
            services.catalog,
        )
    )
    router.include_router(create_data_source_file_router(controller))
    router.include_router(create_data_source_index_router(controller))

    return router


__all__ = [
    "SearchRequestDTO",
    "UpdateIndexCompanyRequestDTO",
    "create_data_source_router",
]
