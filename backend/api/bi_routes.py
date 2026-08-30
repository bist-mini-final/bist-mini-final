"""HTTP and SSE presentation for BI application use cases."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, FastAPI, Path, Request, Response
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette import status

from backend.contracts import ApiErrorDetail, ApiErrorEnvelope
from backend.core.state_stream import SharedStateStream
from backend.core.state_stream_broker import StateStreamBroker
from backend.domains.bi.application import (
    BiApiServices,
    BiApplicationService,
    BiDashboardResult,
)
from backend.domains.bi.application.use_cases import MATERIALIZATION_ACTIVE
from backend.features.bi.api_models import (
    BiCompanyListResponse,
    BiDashboardPendingResponse,
    BiMaterializationAccepted,
    BiMaterializationCandidateListResponse,
)
from backend.features.bi.models import (
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    CompanyId,
    JobId,
    MaterializationStatus,
)
from backend.features.bi.postgres_store import BiPostgresStoreError
from backend.features.bi.question_records import BiQuestionJobProgress

IdentifierPath = Annotated[
    str,
    Path(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        description="기업 또는 작업 식별자",
    ),
]


@dataclass(frozen=True, slots=True)
class BiStateStreams:
    materializations: SharedStateStream[str, BiMaterializationJob]
    questions: SharedStateStream[str, BiQuestionJobProgress]


def _create_state_streams(
    application: BiApplicationService,
    broker: StateStreamBroker | None,
) -> BiStateStreams:
    return BiStateStreams(
        materializations=SharedStateStream(
            application.load_materialization,
            async_loader=application.load_materialization_async,
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
            broker=broker,
            topic_prefix="bi-materialization",
        ),
        questions=SharedStateStream(
            application.load_question_progress,
            async_loader=application.load_question_progress_async,
            fingerprint=lambda progress: (
                progress.queued_questions,
                progress.running_questions,
                progress.completed_questions,
                progress.failed_questions,
            ),
            terminal=lambda progress: (
                progress.queued_questions == 0 and progress.running_questions == 0
            ),
            broker=broker,
            topic_prefix="bi-question-job",
        ),
    )


def _dashboard_response(
    result: BiDashboardResult,
    response: Response,
) -> BiDashboardSnapshot | BiDashboardPendingResponse:
    if result.snapshot is None:
        response.status_code = status.HTTP_202_ACCEPTED
        assert result.pending_job is not None
        return BiDashboardPendingResponse(job=result.pending_job)
    response.headers["ETag"] = f'"{result.snapshot.snapshot.snapshot_id}"'
    return result.snapshot


async def _materialization_events(
    stream: SharedStateStream[str, BiMaterializationJob],
    job_id: str,
    initial: BiMaterializationJob,
    request: Request,
) -> AsyncIterator[dict[str, str]]:
    try:
        async for job in stream.subscribe(job_id, initial=initial):
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
                "data": json.dumps(job.model_dump(mode="json"), ensure_ascii=False),
            }
    except Exception as error:
        yield {
            "event": "error",
            "data": json.dumps(
                {"error": str(error), "job_id": job_id},
                ensure_ascii=False,
            ),
        }


async def _question_events(
    stream: SharedStateStream[str, BiQuestionJobProgress],
    job_id: str,
    initial: BiQuestionJobProgress,
    request: Request,
) -> AsyncIterator[dict[str, str]]:
    try:
        async for progress in stream.subscribe(job_id, initial=initial):
            if await request.is_disconnected():
                return
            terminal = (
                progress.queued_questions == 0 and progress.running_questions == 0
            )
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


def create_bi_router(
    services: BiApiServices,
    *,
    state_stream_broker: StateStreamBroker | None = None,
) -> APIRouter:
    """Wire BI application methods to their stable HTTP contracts."""

    router = APIRouter(prefix="/bi")
    application = BiApplicationService(services)
    streams = _create_state_streams(application, state_stream_broker)

    @router.get(
        "/companies",
        tags=["BI 기업 목록 및 개요"],
        response_model=BiCompanyListResponse,
        summary="BI 등록 기업 목록 및 대시보드 상태 조회",
        description="인덱싱된 전체 기업 목록, 바인딩된 워크북 정보, 최신 머티리얼라이제이션 스냅샷 상태를 반환합니다.",
        responses={500: {"model": ApiErrorEnvelope}},
    )
    async def list_companies() -> BiCompanyListResponse:
        return await application.list_companies()

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
    async def list_materialization_candidates(
    ) -> BiMaterializationCandidateListResponse:
        return await application.list_materialization_candidates()

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
            404: {
                "model": ApiErrorEnvelope,
                "description": "기업 또는 대시보드를 찾을 수 없음",
            },
            500: {"model": ApiErrorEnvelope},
        },
    )
    async def get_dashboard(
        company_id: IdentifierPath,
        response: Response,
    ) -> BiDashboardSnapshot | BiDashboardPendingResponse:
        return _dashboard_response(
            await application.get_dashboard(CompanyId(company_id)),
            response,
        )

    @router.delete(
        "/companies/{company_id}/dashboard",
        tags=["BI 대시보드 스냅샷"],
        status_code=status.HTTP_204_NO_CONTENT,
        summary="기업별 BI 스냅샷 삭제",
        description=(
            "선택 기업의 BI 스냅샷과 파생 질문·답변·작업 기록을 삭제합니다. "
            "원본 Excel 및 pgvector 인덱스는 유지되어 이후 다시 생성할 수 있습니다."
        ),
        responses={
            404: {"model": ApiErrorEnvelope},
            409: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
        },
    )
    async def delete_dashboard(company_id: IdentifierPath) -> Response:
        await application.delete_dashboard(CompanyId(company_id))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

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
            409: {"model": ApiErrorEnvelope, "description": MATERIALIZATION_ACTIVE},
            500: {"model": ApiErrorEnvelope},
        },
    )
    async def create_materialization(
        request: BiMaterializationRequest,
    ) -> BiMaterializationAccepted:
        return await application.create_materialization(request)

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
        return await application.get_materialization(JobId(job_id))

    @router.get(
        "/materializations/{job_id}/stream",
        tags=["BI 머티리얼라이제이션 작업"],
        summary="머티리얼라이제이션 SSE 실시간 진행 스트리밍",
        description="지표 프로파일링 및 질문 생성 진행률을 SSE 이벤트로 실시간 스트리밍합니다.",
        responses={404: {"model": ApiErrorEnvelope}},
    )
    async def stream_materialization(
        job_id: IdentifierPath,
        request: Request,
    ) -> EventSourceResponse:
        initial = await application.load_materialization_async(job_id)
        return EventSourceResponse(
            _materialization_events(
                streams.materializations,
                job_id,
                initial,
                request,
            ),
            ping=15,
        )

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
        return application.refresh_dashboard(CompanyId(company_id))

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
        return application.reset_dashboard(CompanyId(company_id))

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
        return await application.get_question_progress(JobId(job_id))

    @router.get(
        "/question-jobs/{job_id}/stream",
        tags=["BI 지표 질문 및 배치 계산"],
        summary="BI 지표 질문 배치 진행 SSE 스트리밍",
        description="지표 질문 처리 진행 상태를 실시간 Server-Sent Events로 구독합니다.",
        responses={404: {"model": ApiErrorEnvelope}},
    )
    async def stream_question_job(
        job_id: IdentifierPath,
        request: Request,
    ) -> EventSourceResponse:
        initial = await application.load_question_progress_async(job_id)
        return EventSourceResponse(
            _question_events(streams.questions, job_id, initial, request),
            ping=15,
        )

    return router


def register_bi_exception_handlers(application: FastAPI) -> None:
    """Register BI infrastructure failure mapping on the FastAPI application."""

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


__all__ = ["create_bi_router", "register_bi_exception_handlers"]
