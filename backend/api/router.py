from fastapi import APIRouter

from backend.api.auth import SessionAuthenticator, create_auth_router
from backend.bootstrap.application import ApplicationContainer
from backend.domains.benchmark.presentation import create_benchmark_router
from backend.domains.bi.presentation.routes import create_bi_router
from backend.domains.chatbot.presentation import create_chat_router
from backend.domains.company_comparison.presentation.routes import create_company_comparison_router
from backend.domains.data_sources.presentation import (
    create_cell_evidence_router,
    create_data_source_router,
    create_spreadsheet_artifact_router,
)
from backend.domains.operations.presentation import create_job_router
from backend.domains.workflow.presentation import create_module_router, create_workflow_router
from backend.shared.application.state_stream_broker import StateStreamBroker


def create_api_router(
    container: ApplicationContainer,
    *,
    authenticator: SessionAuthenticator,
    state_stream_broker: StateStreamBroker | None = None,
) -> APIRouter:
    """
    Compose version-neutral routes; the application factory owns the public prefix.
    """

    router = APIRouter()
    router.include_router(create_auth_router(authenticator))
    runtime = container.runtime
    services = runtime.services
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
    router.include_router(
        create_spreadsheet_artifact_router(domain.data_sources.artifacts)
    )
    router.include_router(create_cell_evidence_router(domain.data_sources.evidence))
    router.include_router(create_module_router(services.module_registry))
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
