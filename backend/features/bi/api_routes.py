from hashlib import sha256
from typing import Annotated, Final

from fastapi import (
    APIRouter,
    FastAPI,
    HTTPException,
    Path,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from starlette import status

from backend.contracts import ApiErrorDetail, ApiErrorEnvelope

from .api_models import (
    BiCompanyListResponse,
    BiCompanySummary,
    BiDashboardPendingResponse,
    BiMaterializationAccepted,
)
from .api_services import BiApiServices
from .api_state import (
    accepted,
    build_company_summary,
    is_active,
    job_id_for,
    with_refresh_state,
)
from .models import (
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    CompanyId,
    JobId,
    MaterializationStatus,
)
from .postgres_store import BiPostgresStoreError
from .question_batch import BiQuestionBatchPlan
from .question_records import BiQuestionJobProgress
from .question_repository import BiQuestionRegistrationError
from .question_repository_queries import BiQuestionRepositoryError

COMPANY_NOT_FOUND: Final = "company not found"
DASHBOARD_NOT_AVAILABLE: Final = "company dashboard is not available"
JOB_NOT_FOUND: Final = "materialization job not found"
MATERIALIZATION_ACTIVE: Final = "company materialization is active"
QUESTION_JOB_NOT_FOUND: Final = "question job not found"
REFRESH_PERIODS_UNAVAILABLE: Final = "dashboard periods are unavailable"

IdentifierPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


def create_bi_router(services: BiApiServices) -> APIRouter:
    router = APIRouter(prefix="/bi", tags=["BI"])

    @router.get(
        "/companies",
        response_model=BiCompanyListResponse,
        responses={500: {"model": ApiErrorEnvelope}},
    )
    def list_companies() -> BiCompanyListResponse:
        companies: list[BiCompanySummary] = []
        for entry in services.store.list_companies():
            company_id = entry.company.company_id
            snapshot = services.store.get_current(company_id)
            latest_job = services.store.get_latest_job(company_id)
            companies.append(build_company_summary(entry, snapshot, latest_job))
        return BiCompanyListResponse(companies=tuple(companies))

    @router.get(
        "/companies/{company_id}/dashboard",
        response_model=BiDashboardSnapshot | BiDashboardPendingResponse,
        responses={
            202: {"model": BiDashboardPendingResponse},
            404: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def get_dashboard(
        company_id: IdentifierPath,
        response: Response,
    ) -> BiDashboardSnapshot | BiDashboardPendingResponse:
        typed_company_id = CompanyId(company_id)
        company = services.store.get_company(typed_company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, COMPANY_NOT_FOUND)
        snapshot = services.store.get_current(typed_company_id)
        latest_job = services.store.get_latest_job(typed_company_id)
        if snapshot is None:
            if latest_job is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    DASHBOARD_NOT_AVAILABLE,
                )
            response.status_code = status.HTTP_202_ACCEPTED
            return BiDashboardPendingResponse(job=latest_job)
        response.headers["ETag"] = f'"{snapshot.snapshot.snapshot_id}"'
        return with_refresh_state(snapshot, latest_job)

    @router.post(
        "/materializations",
        response_model=BiMaterializationAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        responses={
            409: {
                "model": ApiErrorEnvelope,
                "description": MATERIALIZATION_ACTIVE,
            },
            500: {"model": ApiErrorEnvelope},
        },
    )
    def create_materialization(
        request: BiMaterializationRequest,
    ) -> BiMaterializationAccepted:
        existing = services.store.find_latest_job(
            request.company_id,
            request.source.workbook_hash,
        )
        if (
            existing is not None
            and existing.status is not MaterializationStatus.FAILED
        ):
            return accepted(existing)
        latest_job = services.store.get_latest_job(request.company_id)
        if latest_job is not None and is_active(latest_job.status):
            raise HTTPException(status.HTTP_409_CONFLICT, MATERIALIZATION_ACTIVE)

        job_id = job_id_for(request)
        now = services.clock.now()
        queued = BiMaterializationJob(
            job_id=job_id,
            company_id=request.company_id,
            workbook_hash=request.source.workbook_hash,
            status=MaterializationStatus.QUEUED,
            completed_requests=0,
            total_requests=0,
            started_at=now,
            updated_at=now,
        )
        try:
            persisted = services.materializations.enqueue(request, queued)
        except BiPostgresStoreError as error:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "BI Kubernetes queue is unavailable",
            ) from error
        return accepted(persisted)

    @router.get(
        "/materializations/{job_id}",
        response_model=BiMaterializationJob,
        responses={
            404: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def get_materialization(job_id: IdentifierPath) -> BiMaterializationJob:
        job = services.store.get_job(JobId(job_id))
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, JOB_NOT_FOUND)
        return job

    @router.post(
        "/companies/{company_id}/refresh",
        response_model=BiQuestionJobProgress,
        status_code=status.HTTP_202_ACCEPTED,
        responses={
            404: {"model": ApiErrorEnvelope},
            409: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def refresh_dashboard(company_id: IdentifierPath) -> BiQuestionJobProgress:
        typed_company_id = CompanyId(company_id)
        company = services.store.get_company(typed_company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, COMPANY_NOT_FOUND)
        snapshot = services.store.get_current(typed_company_id)
        if snapshot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, DASHBOARD_NOT_AVAILABLE)
        if not snapshot.periods:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                REFRESH_PERIODS_UNAVAILABLE,
            )
        created_at = services.clock.now()
        identity = "\x00".join(
            (
                str(typed_company_id),
                snapshot.source.workbook_hash,
                str(snapshot.source.index_id),
                created_at.isoformat(),
            )
        )
        job_id = JobId(
            "question-job-"
            + sha256(identity.encode("utf-8")).hexdigest()[:24]
        )
        try:
            return services.questions.queue_materialization_questions(
                BiQuestionBatchPlan(
                    materialization=BiMaterializationRequest(
                        company_id=company.company_id,
                        display_name=company.display_name,
                        source=snapshot.source,
                    ),
                    periods=snapshot.periods,
                    job_id=job_id,
                    created_at=created_at,
                )
            )
        except (BiQuestionRepositoryError, BiQuestionRegistrationError) as error:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "BI question Kubernetes queue is unavailable",
            ) from error

    @router.get(
        "/question-jobs/{job_id}",
        response_model=BiQuestionJobProgress,
        responses={
            404: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def get_question_job(job_id: IdentifierPath) -> BiQuestionJobProgress:
        progress = services.questions.get_job_progress(JobId(job_id))
        if progress is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, QUESTION_JOB_NOT_FOUND)
        return progress

    return router


def register_bi_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(BiPostgresStoreError)
    def handle_store_failure(
        _request: Request,
        _error: BiPostgresStoreError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ApiErrorEnvelope(
                detail=ApiErrorDetail(
                    code="BI_STORE_UNAVAILABLE",
                    message="BI PostgreSQL store is unavailable",
                    retryable=True,
                )
            ).model_dump(mode="json"),
        )
