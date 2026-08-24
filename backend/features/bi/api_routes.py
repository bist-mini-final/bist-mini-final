"""HTTP API endpoints for BI Company Profiling, Materialization Jobs, and Live Snapshots."""

from __future__ import annotations

import json
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
from sse_starlette.sse import EventSourceResponse
from starlette import status

from backend.contracts import ApiErrorDetail, ApiErrorEnvelope
from backend.core.state_stream import SharedStateStream

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

IdentifierPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", description="기업 또는 작업 식별자")]


def create_bi_router(services: BiApiServices) -> APIRouter:
    """Create and configure the FastAPI router for enterprise BI analytics endpoints.

    Args:
        services: Domain services for company catalog, materializations, questions, and snapshots.

    Returns:
        Configured APIRouter with hierarchical OpenAPI tags.
    """
    router = APIRouter(prefix="/bi")

    def load_materialization(job_id: str) -> BiMaterializationJob:
        job = services.store.get_job(JobId(job_id))
        if job is None:
            raise LookupError(JOB_NOT_FOUND)
        if job.status is MaterializationStatus.MATERIALIZING:
            progress = services.questions.get_job_progress(JobId(job_id))
            if progress is not None:
                completed = (
                    progress.completed_questions + progress.failed_questions
                )
                job = job.model_copy(
                    update={
                        "completed_requests": completed,
                        "total_requests": progress.total_questions,
                        "message": (
                            f"지표 질문 {completed}/{progress.total_questions}건을 "
                            "병렬 처리했습니다."
                        ),
                    }
                )
        return job

    def load_question_progress(job_id: str) -> BiQuestionJobProgress:
        progress = services.questions.get_job_progress(JobId(job_id))
        if progress is None:
            raise LookupError(QUESTION_JOB_NOT_FOUND)
        return progress

    materialization_stream = SharedStateStream(
        load_materialization,
        fingerprint=lambda job: (
            job.updated_at,
            job.status,
            job.completed_requests,
            job.total_requests,
        ),
        terminal=lambda job: job.status
        in (
            MaterializationStatus.READY,
            MaterializationStatus.PARTIAL,
            MaterializationStatus.FAILED,
        ),
    )
    question_stream = SharedStateStream(
        load_question_progress,
        fingerprint=lambda progress: (
            progress.queued_questions,
            progress.running_questions,
            progress.completed_questions,
            progress.failed_questions,
        ),
        terminal=lambda progress: (
            progress.queued_questions == 0 and progress.running_questions == 0
        ),
    )

    @router.get(
        "/companies",
        tags=["BI 기업 목록 및 개요"],
        response_model=BiCompanyListResponse,
        summary="BI 등록 기업 목록 및 대시보드 상태 조회",
        description="인덱싱된 전체 기업 목록, 바인딩된 워크북 정보, 최신 머티리얼라이제이션 스냅샷 상태를 반환합니다.",
        responses={500: {"model": ApiErrorEnvelope}},
    )
    def list_companies() -> BiCompanyListResponse:
        """인덱싱된 전체 기업 목록 및 활성 스냅샷 요약 정보를 반환합니다."""
        entries = services.store.list_companies()
        if not entries:
            return BiCompanyListResponse(companies=())
        company_ids = tuple(entry.company.company_id for entry in entries)
        snapshots = services.store.get_current_many(company_ids)
        latest_jobs = services.store.get_latest_jobs(company_ids)
        companies: list[BiCompanySummary] = []
        for entry in entries:
            company_id = entry.company.company_id
            companies.append(
                build_company_summary(
                    entry,
                    snapshots.get(company_id),
                    latest_jobs.get(company_id),
                )
            )
        return BiCompanyListResponse(companies=tuple(companies))

    @router.get(
        "/companies/{company_id}/dashboard",
        tags=["BI 대시보드 스냅샷"],
        response_model=BiDashboardSnapshot | BiDashboardPendingResponse,
        summary="기업별 최신 BI 대시보드 스냅샷 조회",
        description=(
            "지정된 기업의 재무 지표 시계열, 공식 계산 결과, 출처 셀 링크 및 "
            "데이터 검증 이슈가 포함된 최신 BI 대시보드 스냅샷을 반환합니다."
        ),
        responses={
            202: {"model": BiDashboardPendingResponse, "description": "머티리얼라이제이션 작업 진행 중"},
            404: {"model": ApiErrorEnvelope, "description": "기업 또는 대시보드를 찾을 수 없음"},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def get_dashboard(
        company_id: IdentifierPath,
        response: Response,
    ) -> BiDashboardSnapshot | BiDashboardPendingResponse:
        """특정 기업의 발행된 BI 대시보드 완성형 스냅샷을 반환합니다."""
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
        tags=["BI 머티리얼라이제이션 작업"],
        response_model=BiMaterializationAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        summary="BI 머티리얼라이제이션 작업 큐 등록",
        description=(
            "기업의 스프레드시트 구조를 프로파일링하고, 필수 재무 질문들을 일괄 생성하여 "
            "Kubernetes KEDA 큐(`bi_materialization_jobs`, `bi_questions`)에 등록합니다."
        ),
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
        """BI 메트릭 및 공식 추출을 위한 백그라운드 머티리얼라이제이션 작업을 큐에 등록합니다."""
        existing = services.store.find_latest_job(request.company_id)
        if existing is not None and existing.status is not MaterializationStatus.FAILED:
            if existing.workbook_hash == request.source.workbook_hash:
                return accepted(existing)
            if is_active(existing.status):
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
        tags=["BI 머티리얼라이제이션 작업"],
        response_model=BiMaterializationJob,
        summary="머티리얼라이제이션 작업 상태 조회",
        description="진행 중이거나 완료된 머티리얼라이제이션 작업의 진행 건수, 상태, 에러 메시지를 조회합니다.",
        responses={
            404: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def get_materialization(job_id: IdentifierPath) -> BiMaterializationJob:
        """머티리얼라이제이션 작업의 현재 실행 진행 상태를 반환합니다."""
        job = services.store.get_job(JobId(job_id))
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, JOB_NOT_FOUND)
        return job

    @router.get(
        "/materializations/{job_id}/stream",
        tags=["BI 머티리얼라이제이션 작업"],
        summary="머티리얼라이제이션 SSE 실시간 진행 스트리밍",
        description="지표 프로파일링 및 질문 생성 진행률을 SSE 이벤트로 실시간 스트리밍합니다.",
        responses={404: {"model": ApiErrorEnvelope}},
    )
    async def stream_materialization(job_id: IdentifierPath, request: Request):
        """활성 머티리얼라이제이션 작업의 실시간 진행 이벤트를 스트리밍합니다."""
        try:
            initial = load_materialization(job_id)
        except LookupError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, JOB_NOT_FOUND) from error

        async def events():
            try:
                async for job in materialization_stream.subscribe(job_id, initial=initial):
                    if await request.is_disconnected():
                        return
                    terminal = job.status in (
                        MaterializationStatus.READY,
                        MaterializationStatus.PARTIAL,
                        MaterializationStatus.FAILED,
                    )
                    yield {
                        "event": (
                            "materialization_completed"
                            if terminal
                            else "materialization_progress"
                        ),
                        "data": json.dumps(
                            job.model_dump(mode="json"),
                            ensure_ascii=False,
                        ),
                    }
            except Exception as error:
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"error": str(error), "job_id": job_id},
                        ensure_ascii=False,
                    ),
                }

        return EventSourceResponse(events())

    @router.post(
        "/companies/{company_id}/refresh",
        tags=["BI 지표 질문 및 배치 계산"],
        response_model=BiQuestionJobProgress,
        status_code=status.HTTP_202_ACCEPTED,
        summary="기존 대시보드 지표 일괄 재계산 요청",
        description="저장된 기간(Periods)과 공식들에 대해 지표 추출 질문들을 다시 큐에 등록하여 최신화합니다.",
        responses={
            404: {"model": ApiErrorEnvelope},
            409: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def refresh_dashboard(company_id: IdentifierPath) -> BiQuestionJobProgress:
        """대시보드 지표 관측값을 갱신하기 위해 질문 추출 배치를 큐에 등록합니다."""
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
        tags=["BI 지표 질문 및 배치 계산"],
        response_model=BiQuestionJobProgress,
        summary="BI 지표 질문 배치 작업 진행률 조회",
        description="병렬 처리 중인 대기(queued), 진행(running), 완료(completed), 실패(failed) 질문 건수를 반환합니다.",
        responses={
            404: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def get_question_job(job_id: IdentifierPath) -> BiQuestionJobProgress:
        """병렬 질문 배치 작업의 진행 건수 집계를 반환합니다."""
        progress = services.questions.get_job_progress(JobId(job_id))
        if progress is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, QUESTION_JOB_NOT_FOUND)
        return progress

    @router.get(
        "/question-jobs/{job_id}/stream",
        tags=["BI 지표 질문 및 배치 계산"],
        summary="BI 지표 질문 배치 진행 SSE 스트리밍",
        description="지표 질문 처리 진행 상태를 실시간 Server-Sent Events로 구독합니다.",
        responses={404: {"model": ApiErrorEnvelope}},
    )
    async def stream_question_job(job_id: IdentifierPath, request: Request):
        """병렬 질문 배치 작업의 실시간 진행 이벤트를 스트리밍합니다."""
        try:
            initial = load_question_progress(job_id)
        except LookupError as error:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                QUESTION_JOB_NOT_FOUND,
            ) from error

        async def events():
            try:
                async for progress in question_stream.subscribe(
                    job_id,
                    initial=initial,
                ):
                    if await request.is_disconnected():
                        return
                    terminal = (
                        progress.queued_questions == 0
                        and progress.running_questions == 0
                    )
                    yield {
                        "event": (
                            "question_job_completed"
                            if terminal
                            else "question_job_progress"
                        ),
                        "data": json.dumps(
                            progress.model_dump(mode="json"),
                            ensure_ascii=False,
                        ),
                    }
            except Exception as error:
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"error": str(error), "job_id": job_id},
                        ensure_ascii=False,
                    ),
                }

        return EventSourceResponse(events())

    return router


def register_bi_exception_handlers(application: FastAPI) -> None:
    """Register BI domain exception handlers on the FastAPI application."""

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
