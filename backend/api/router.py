from fastapi import APIRouter

from backend.bootstrap.container import ApplicationContainer
from backend.core.state_stream_broker import StateStreamBroker
from backend.features.bi.api_routes import create_bi_router
from backend.features.chatbot.api_routes import create_chat_router
from backend.features.company_comparison.api_routes import (
    create_company_comparison_router,
)

from .benchmark_routes import create_benchmark_router
from .cell_evidence_routes import create_cell_evidence_router
from .data_source_routes import create_data_source_router
from .job_routes import create_job_router
from .module_routes import create_module_router
from .spreadsheet_artifact_routes import create_spreadsheet_artifact_router
from .workflow_routes import create_workflow_router


def create_api_router(
    container: ApplicationContainer,
    *,
    state_stream_broker: StateStreamBroker | None = None,
) -> APIRouter:
    """
    Compose version-neutral routes; the application factory owns the public prefix.
    """

    router = APIRouter()
    runtime = container.runtime
    services = runtime.services
    paths = runtime.paths
    domain = container.domain
    execution = container.execution
    router.include_router(
        create_bi_router(domain.bi_services, state_stream_broker=state_stream_broker)
    )
    router.include_router(
        create_company_comparison_router(domain.company_comparison)
    )
    workflow_dispatcher = execution.workflow_dispatcher
    workflow_execution = execution.workflow_execution
    workflow_store = services.workflow_store
    run_store = services.run_store
    workflow_executor = services.workflow_executor
    chat_router = create_chat_router(
        db_manager=services.db_manager,
        workflow_store=workflow_store,
        run_store=run_store,
        workflow_executor=workflow_executor,
        workflow_dispatcher=workflow_dispatcher,
        completion_client=runtime.completion_client,
        bi_services=domain.bi_services,
        suggestion_service=domain.chat_suggestions,
        pgvector_store=services.pgvector_store,
        prefix="",
    )
    router.include_router(chat_router, prefix="/chat")
    router.include_router(
        chat_router,
        prefix="/chatbot",
        include_in_schema=False,
    )
    router.include_router(create_job_router(domain.job_monitor))
    pgvector_store = services.pgvector_store
    router.include_router(create_module_router())
    router.include_router(create_spreadsheet_artifact_router(paths.spreadsheet_artifact_dir))
    router.include_router(
        create_cell_evidence_router(
            pgvector_store=pgvector_store,
            processed_dir=paths.processed_dir,
            artifact_dir=paths.spreadsheet_artifact_dir,
        )
    )
    router.include_router(
        create_workflow_router(
            workflow_store=workflow_store,
            run_store=run_store,
            workflow_execution=workflow_execution,
            state_stream_broker=state_stream_broker,
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
            run_store=run_store,
            workflow_execution=workflow_execution,
        )
    )
    return router
