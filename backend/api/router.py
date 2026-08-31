from fastapi import APIRouter

from backend.bootstrap.application import ApplicationContainer
from backend.domains.benchmark.presentation import create_benchmark_router
from backend.domains.bi.presentation.routes import create_bi_router
from backend.domains.chatbot.presentation import create_chat_router
from backend.domains.company_comparison.presentation.routes import create_company_comparison_router
from backend.domains.data_sources.presentation import create_data_source_router
from backend.domains.operations.presentation import create_job_router
from backend.domains.workflow.presentation import create_workflow_router
from backend.shared.application.state_stream_broker import StateStreamBroker

from .cell_evidence_routes import create_cell_evidence_router
from .module_routes import create_module_router
from .spreadsheet_artifact_routes import create_spreadsheet_artifact_router


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
    workflow_execution = execution.workflow_execution
    workflow_store = services.workflow_store
    run_store = services.run_store
    chat_router = create_chat_router(domain.chatbot, prefix="")
    router.include_router(chat_router, prefix="/chat")
    router.include_router(
        chat_router,
        prefix="/chatbot",
        include_in_schema=False,
    )
    router.include_router(create_job_router(domain.operations))
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
        create_data_source_router(domain.data_sources)
    )
    router.include_router(
        create_benchmark_router(domain.benchmark)
    )
    return router
