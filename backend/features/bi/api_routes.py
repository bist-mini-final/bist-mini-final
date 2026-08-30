"""HTTP API endpoints for BI Company Profiling, Materialization Jobs, and Live Snapshots."""

from __future__ import annotations

import asyncio
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
from backend.core.state_stream_broker import StateStreamBroker

from .api_models import (
    BiCompanyListResponse,
    BiCompanySummary,
    BiDashboardPendingResponse,
    BiMaterializationAccepted,
    BiMaterializationCandidateListResponse,
)
from .api_services import BiApiServices
from .api_state import (
    accepted,
    build_company_summary,
    build_materialization_candidate,
    is_active,
    job_id_for,
    with_refresh_state,
)
from .dashboard_recalculation import (
    BiDashboardRecalculationError,
    recalculate_dashboard,
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
from .question_repository import (
    BiQuestionRegistrationError,
    BiQuestionResetActiveError,
)
from .question_repository_queries import BiQuestionRepositoryError

COMPANY_NOT_FOUND: Final = "company not found"
DASHBOARD_NOT_AVAILABLE: Final = "company dashboard is not available"
JOB_NOT_FOUND: Final = "materialization job not found"
MATERIALIZATION_ACTIVE: Final = "company materialization is active"
QUESTION_JOB_NOT_FOUND: Final = "question job not found"
REFRESH_PERIODS_UNAVAILABLE: Final = "dashboard periods are unavailable"

IdentifierPath = Annotated[
    str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", description="기업 또는 작업 식별자")
]


def create_bi_router(
    services: BiApiServices,
    *,
    state_stream_broker: StateStreamBroker | None = None,
) -> APIRouter:
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
                completed = progress.completed_questions + progress.failed_questions
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

    async def load_materialization_async(job_id: str) -> BiMaterializationJob:
        job = await services.store.get_job_async(JobId(job_id))
        if job is None:
            raise LookupError(JOB_NOT_FOUND)
        if job.status is MaterializationStatus.MATERIALIZING:
            progress = await services.questions.get_job_progress_async(JobId(job_id))
            if progress is not None:
                completed = progress.completed_questions + progress.failed_questions
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

    async def load_question_progress_async(job_id: str) -> BiQuestionJobProgress:
        progress = await services.questions.get_job_progress_async(JobId(job_id))
        if progress is None:
            raise LookupError(QUESTION_JOB_NOT_FOUND)
        return progress

    materialization_stream = SharedStateStream(
        load_materialization,
        async_loader=load_materialization_async,
        fingerprint=lambda job: (
            job.updated_at,
            job.status,
            job.completed_requests,
            job.total_requests,
        ),
        terminal=lambda job: (
            job.status
            in (
                MaterializationStatus.READY,
                MaterializationStatus.PARTIAL,
                MaterializationStatus.FAILED,
            )
        ),
        broker=state_stream_broker,
        topic_prefix="bi-materialization",
    )
    question_stream = SharedStateStream(
        load_question_progress,
        async_loader=load_question_progress_async,
        fingerprint=lambda progress: (
            progress.queued_questions,
            progress.running_questions,
            progress.completed_questions,
            progress.failed_questions,
        ),
        terminal=lambda progress: (
            progress.queued_questions == 0 and progress.running_questions == 0
        ),
        broker=state_stream_broker,
        topic_prefix="bi-question-job",
    )

    @router.get(
        "/companies",
        tags=["BI 기업 목록 및 개요"],
        response_model=BiCompanyListResponse,
        summary="BI 등록 기업 목록 및 대시보드 상태 조회",
        description="인덱싱된 전체 기업 목록, 바인딩된 워크북 정보, 최신 머티리얼라이제이션 스냅샷 상태를 반환합니다.",
        responses={500: {"model": ApiErrorEnvelope}},
    )
    async def list_companies() -> BiCompanyListResponse:
        """인덱싱된 전체 기업 목록 및 활성 스냅샷 요약 정보를 반환합니다."""
        entries = await services.store.list_companies_async()
        if not entries:
            return BiCompanyListResponse(companies=())
        company_ids = tuple(entry.company.company_id for entry in entries)
        snapshots, latest_jobs = await asyncio.gather(
            services.store.get_current_many_async(company_ids),
            services.store.get_latest_jobs_async(company_ids),
        )
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
        "/materialization-candidates",
        tags=["BI 머티리얼라이제이션 작업"],
        response_model=BiMaterializationCandidateListResponse,
        summary="BI 스냅샷 생성 후보 기업 조회",
        description=(
            "인덱싱은 완료됐지만 최신 원본에 대응하는 BI 스냅샷이 없고, "
            "현재 생성 작업도 실행 중이지 않은 기업을 반환합니다."
        ),
        responses={500: {"model": ApiErrorEnvelope}},
    )
    async def list_materialization_candidates() -> BiMaterializationCandidateListResponse:
        """Return indexed companies that a user may explicitly add to BI."""
        entries = await services.store.list_companies_async()
        if not entries:
            return BiMaterializationCandidateListResponse(candidates=())
        company_ids = tuple(entry.company.company_id for entry in entries)
        snapshots, latest_jobs = await asyncio.gather(
            services.store.get_current_many_async(company_ids),
            services.store.get_latest_jobs_async(company_ids),
        )
        candidates = tuple(
            candidate
            for entry in entries
            if (
                candidate := build_materialization_candidate(
                    entry,
                    snapshots.get(entry.company.company_id),
                    latest_jobs.get(entry.company.company_id),
                )
            ) is not None
        )
        return BiMaterializationCandidateListResponse(candidates=candidates)

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
            202: {
                "model": BiDashboardPendingResponse,
                "description": "머티리얼라이제이션 작업 진행 중",
            },
            404: {"model": ApiErrorEnvelope, "description": "기업 또는 대시보드를 찾을 수 없음"},
            500: {"model": ApiErrorEnvelope},
        },
    )
    async def get_dashboard(
        company_id: IdentifierPath,
        response: Response,
    ) -> BiDashboardSnapshot | BiDashboardPendingResponse:
        """특정 기업의 발행된 BI 대시보드 완성형 스냅샷을 반환합니다."""
        typed_company_id = CompanyId(company_id)
        company, snapshot, latest_job = await asyncio.gather(
            services.store.get_company_async(typed_company_id),
            services.store.get_current_async(typed_company_id),
            services.store.get_latest_job_async(typed_company_id),
        )
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, COMPANY_NOT_FOUND)
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
    async def create_materialization(
        request: BiMaterializationRequest,
    ) -> BiMaterializationAccepted:
        """BI 메트릭 및 공식 추출을 위한 백그라운드 머티리얼라이제이션 작업을 큐에 등록합니다."""
        existing = await services.store.find_latest_job_async(request.company_id)
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
            persisted = await services.materializations.enqueue_async(request, queued)
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
    async def get_materialization(job_id: IdentifierPath) -> BiMaterializationJob:
        """머티리얼라이제이션 작업의 현재 실행 진행 상태를 반환합니다."""
        job = await services.store.get_job_async(JobId(job_id))
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
            initial = await load_materialization_async(job_id)
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
                            "materialization_completed" if terminal else "materialization_progress"
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

        return EventSourceResponse(events(), ping=15)

    @router.post(
        "/companies/{company_id}/refresh",
        tags=["BI 지표 질문 및 배치 계산"],
        response_model=BiDashboardSnapshot,
        summary="현재 관측값으로 대시보드 재계산",
        description="질문과 답변을 추가하지 않고 현재 원천 관측값으로 파생 지표와 스냅샷을 다시 계산합니다.",
        responses={
            404: {"model": ApiErrorEnvelope},
            409: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    def refresh_dashboard(company_id: IdentifierPath) -> BiDashboardSnapshot:
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
                str(snapshot.snapshot.snapshot_id),
                snapshot.source.workbook_hash,
                str(snapshot.source.index_id),
                created_at.isoformat(),
            )
        )
        job_id = JobId("recalculation-" + sha256(identity.encode("utf-8")).hexdigest()[:24])
        try:
            return recalculate_dashboard(
                store=services.store,
                company_id=typed_company_id,
                job_id=job_id,
                generated_at=created_at,
            )
        except BiDashboardRecalculationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post(
        "/companies/{company_id}/reset",
        tags=["BI 지표 질문 및 배치 계산"],
        response_model=BiQuestionJobProgress,
        status_code=status.HTTP_202_ACCEPTED,
        summary="질의응답 데이터 초기화 및 재생성",
        description="선택 기업의 현재 원본 질의응답을 트랜잭션으로 교체하고 새 질문 배치를 큐에 등록합니다.",
        responses={
            404: {"model": ApiErrorEnvelope},
            409: {"model": ApiErrorEnvelope},
            503: {"model": ApiErrorEnvelope},
        },
    )
    def reset_dashboard(company_id: IdentifierPath) -> BiQuestionJobProgress:
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
        job_id = JobId("question-reset-" + sha256(identity.encode("utf-8")).hexdigest()[:24])
        try:
            return services.questions.reset_materialization_questions(
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
        except BiQuestionResetActiveError as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "BI questions are already active for this company",
            ) from error
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
    async def get_question_job(job_id: IdentifierPath) -> BiQuestionJobProgress:
        """병렬 질문 배치 작업의 진행 건수 집계를 반환합니다."""
        progress = await services.questions.get_job_progress_async(JobId(job_id))
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
            initial = await load_question_progress_async(job_id)
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
                    terminal = progress.queued_questions == 0 and progress.running_questions == 0
                    yield {
                        "event": (
                            "question_job_completed" if terminal else "question_job_progress"
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

        return EventSourceResponse(events(), ping=15)

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
