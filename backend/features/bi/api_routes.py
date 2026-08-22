from hashlib import sha256
from typing import Annotated, Final

from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Path,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from starlette import status

from .api_models import (
    BiApiFailure,
    BiCompanyListResponse,
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
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    CompanyId,
    JobId,
    MaterializationStatus,
)
from .question_batch import BiQuestionBatchPlan
from .question_records import BiQuestionJobProgress
from .snapshot_store import BiSnapshotStoreCorruption


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
        responses={500: {"model": BiApiFailure}},
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
            404: {"model": BiApiFailure},
            500: {"model": BiApiFailure},
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
        if (
            snapshot is None
            and latest_job is not None
            and services.initial_snapshots is not None
        ):
            snapshot = services.initial_snapshots.materialize(
                company,
                latest_job.workbook_hash,
            )
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
                "model": BiApiFailure,
                "description": MATERIALIZATION_ACTIVE,
            },
            500: {"model": BiApiFailure},
        },
    )
    def create_materialization(
        request: BiMaterializationRequest,
        background_tasks: BackgroundTasks,
    ) -> BiMaterializationAccepted:
        existing = services.store.find_latest_job(
            request.company_id,
            request.source.workbook_hash,
        )
        if existing is not None:
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
        services.store.register_company(
            BiCompany(
                company_id=request.company_id,
                display_name=request.display_name,
            )
        )
        services.store.save_job(queued)
        background_tasks.add_task(services.runner.materialize, request, job_id)
        return accepted(queued)

    @router.get(
        "/materializations/{job_id}",
        response_model=BiMaterializationJob,
        responses={
            404: {"model": BiApiFailure},
            500: {"model": BiApiFailure},
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
            404: {"model": BiApiFailure},
            409: {"model": BiApiFailure},
            500: {"model": BiApiFailure},
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

    @router.get(
        "/question-jobs/{job_id}",
        response_model=BiQuestionJobProgress,
        responses={
            404: {"model": BiApiFailure},
            500: {"model": BiApiFailure},
        },
    )
    def get_question_job(job_id: IdentifierPath) -> BiQuestionJobProgress:
        progress = services.questions.get_job_progress(JobId(job_id))
        if progress is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, QUESTION_JOB_NOT_FOUND)
        return progress

    return router


def create_bi_app(services: BiApiServices) -> FastAPI:
    application = FastAPI(
        title="BI Materialization API",
        version="1.0.0",
        openapi_tags=[
            {
                "name": "BI",
                "description": "지표 스냅샷 조회와 materialization 작업 관리",
            }
        ],
    )
    mount_bi_api(application, services)
    return application


def mount_bi_api(application: FastAPI, services: BiApiServices) -> None:
    register_bi_exception_handlers(application)
    application.include_router(create_bi_router(services), prefix="/api")


def register_bi_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(BiSnapshotStoreCorruption)
    def handle_store_corruption(
        _request: Request,
        _error: BiSnapshotStoreCorruption,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=BiApiFailure(detail="BI artifact is corrupted").model_dump(),
        )
