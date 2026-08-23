from fastapi import APIRouter

from backend.bootstrap.container import ApplicationContainer
from backend.features.bi.api_routes import create_bi_router

from .benchmark_routes import create_benchmark_router
from .data_source_routes import create_data_source_router
from .module_routes import create_module_router
from .spreadsheet_artifact_routes import create_spreadsheet_artifact_router
from .workflow_routes import create_workflow_router


def create_api_router(container: ApplicationContainer) -> APIRouter:
    """
    Compose the application's `/api` router with shared services and domain-specific endpoints.
    """

    router = APIRouter(prefix="/api")
    runtime = container.runtime
    services = runtime.services
    paths = runtime.paths
    module_registry = services.module_registry
    router.include_router(create_bi_router(container.bi_services))
    workflow_dispatcher = container.workflow_dispatcher
    workflow_store = services.workflow_store
    run_store = services.run_store
    workflow_executor = services.workflow_executor
    pgvector_store = services.pgvector_store
    router.include_router(create_module_router(module_registry))
    router.include_router(
        create_spreadsheet_artifact_router(paths.spreadsheet_artifact_dir)
    )
    router.include_router(
        create_workflow_router(
            workflow_store=workflow_store,
            run_store=run_store,
            workflow_executor=workflow_executor,
            workflow_dispatcher=workflow_dispatcher,
        )
    )
    router.include_router(
        create_data_source_router(
            processed_dir=paths.processed_dir,
            embedding_encoder=runtime.embedding_encoder,
            pgvector_store=pgvector_store,
            connection_probe=runtime.pgvector_probe,
            db_manager=services.db_manager,
            workflow_store=workflow_store,
            run_store=run_store,
            workflow_executor=workflow_executor,
            workflow_dispatcher=workflow_dispatcher,
        )
    )
    router.include_router(
        create_benchmark_router(
            workflow_store=workflow_store,
            workflow_executor=workflow_executor,
            workflow_dispatcher=workflow_dispatcher,
        )
    )
    return router
