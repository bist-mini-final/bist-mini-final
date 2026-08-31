"""HTTP route wiring for workflow definitions, runs, and SSE telemetry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi import Path as FastPath
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.domains.workflow.application.services import (
    WorkflowCommandService,
    WorkflowQueryService,
)
from backend.engine.workflows import (
    RunNodeState,
    RunStore,
    WorkflowDocument,
    WorkflowExecutionPort,
    WorkflowExecutionRequest,
    WorkflowRun,
    WorkflowSaveRequest,
    WorkflowStore,
)
from backend.shared.application.state_stream import SharedStateStream
from backend.shared.application.state_stream_broker import StateStreamBroker

from .workflow_controller import WorkflowHttpController


class WorkflowListResponse(BaseModel):
    """저장된 전체 DAG 워크플로 정의 목록 응답 DTO."""

    workflows: List[WorkflowDocument] = Field(
        ..., description="표준/사용자 메타데이터를 포함한 전체 DAG 워크플로 목록"
    )


class WorkflowDeleteResponse(BaseModel):
    """워크플로 삭제 성공 응답 DTO."""

    deleted: str = Field(..., description="삭제된 워크플로 ID")


class RunListResponse(BaseModel):
    """워크플로 실행 요약 기록 목록 응답 DTO."""

    runs: List[WorkflowRun] = Field(..., description="워크플로 실행 기록 목록")


def _create_cache_router(controller: WorkflowHttpController) -> APIRouter:
    router = APIRouter()

    @router.delete(
        "/cache",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="런타임 캐시 및 실행 아티팩트 전체 초기화",
        description="실행 중인 워크플로가 없을 때 임베딩, 검색 결과, 임시 파일 캐시를 모두 삭제합니다.",
    )
    def clear_runtime_cache() -> Dict[str, Any]:
        return controller.clear_runtime_cache()

    return router


def _create_workflow_definition_router(controller: WorkflowHttpController) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/workflows",
        tags=["워크플로 정의 관리"],
        response_model=WorkflowListResponse,
        summary="저장된 DAG 워크플로 목록 조회",
        description="시스템에 저장된 모든 RAG/시계열 파이프라인 DAG 워크플로 정의 목록을 반환합니다.",
    )
    def list_workflows() -> Dict[str, Any]:
        return controller.list_workflows()

    @router.get(
        "/workflows/{workflow_id}",
        tags=["워크플로 정의 관리"],
        summary="단일 DAG 워크플로 상세 정의 조회",
        description="지정된 `workflow_id`의 노드(Node), 엣지(Edge), 모듈 설정 및 뷰포트 상태를 조회합니다.",
    )
    def get_workflow(
        workflow_id: str = FastPath(..., description="조회할 워크플로 식별자"),
    ) -> WorkflowDocument:
        return controller.get_workflow(workflow_id)

    @router.put(
        "/workflows/{workflow_id}",
        tags=["워크플로 정의 관리"],
        summary="DAG 워크플로 생성 또는 업데이트 저장",
        description="XYFlow 캔버스에서 편집된 노드 연결 및 모듈 설정을 워크플로 저장소에 영속화합니다.",
    )
    def save_workflow(
        workflow_id: str = FastPath(..., description="저장할 워크플로 식별자"),
        request: WorkflowSaveRequest = None,  # type: ignore[assignment]
    ) -> WorkflowDocument:
        return controller.save_workflow(workflow_id, request)

    @router.delete(
        "/workflows/{workflow_id}",
        tags=["워크플로 정의 관리"],
        response_model=WorkflowDeleteResponse,
        summary="DAG 워크플로 삭제",
        description="저장소에서 해당 워크플로 정의를 영구 삭제합니다.",
    )
    def delete_workflow(
        workflow_id: str = FastPath(..., description="삭제할 워크플로 식별자"),
    ) -> Dict[str, str]:
        return controller.delete_workflow(workflow_id)

    return router


def create_workflow_router(
    *,
    workflow_store: WorkflowStore,
    run_store: RunStore,
    workflow_execution: WorkflowExecutionPort,
    state_stream_broker: StateStreamBroker | None = None,
) -> APIRouter:
    """Wire stable workflow HTTP endpoints to command/query application services."""

    router = APIRouter()
    run_stream = SharedStateStream(
        run_store.load_summary,
        fingerprint=lambda run: run.updated_at,
        terminal=lambda run: run.status in ("completed", "failed", "paused"),
        broker=state_stream_broker,
        topic_prefix="workflow-run",
    )
    controller = WorkflowHttpController(
        WorkflowCommandService(workflow_store, workflow_execution),
        WorkflowQueryService(workflow_store, run_store),
        run_stream,
    )
    router.include_router(_create_cache_router(controller))
    router.include_router(_create_workflow_definition_router(controller))

    @router.post(
        "/workflows/{workflow_id}/runs",
        tags=["워크플로 실행 및 실시간 스트림"],
        status_code=202,
        summary="Kubernetes 비동기 워크플로 실행 요청 등록",
        description=(
            "지정된 워크플로를 입력 데이터와 함께 PostgreSQL 큐(`workflow_runs`)에 등록하고, "
            "KEDA 워커가 백그라운드에서 DAG 모듈들을 토폴로지 순서로 병렬 실행하도록 합니다."
        ),
    )
    def create_workflow_run(
        workflow_id: str = FastPath(..., description="실행할 워크플로 식별자"),
        request: WorkflowExecutionRequest = None,  # type: ignore[assignment]
    ) -> WorkflowRun:
        return controller.submit_run(workflow_id, request)

    @router.get(
        "/runs",
        tags=["워크플로 실행 및 실시간 스트림"],
        response_model=RunListResponse,
        summary="워크플로 실행 기록 목록 조회",
        description="전체 또는 특정 워크플로의 이전 실행 상태, 소요 시간, 노드 성공/실패 기록을 조회합니다.",
    )
    def list_runs(
        workflow_id: Optional[str] = Query(
            default=None,
            description="특정 워크플로 필터링 ID",
        ),
        limit: int = Query(
            default=50,
            ge=1,
            le=200,
            description="반환할 최대 실행 수",
        ),
    ) -> Dict[str, Any]:
        return controller.list_runs(workflow_id, limit)

    @router.get(
        "/runs/{run_id}",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="단일 워크플로 실행 상태 및 노드 결과 상세 조회",
        description="지정된 실행(`run_id`)의 실시간 상태, 각 노드별 입력/출력 데이터, 토큰 비용, 지연 시간을 반환합니다.",
    )
    def get_run(
        run_id: str = FastPath(..., description="조회할 실행 ID"),
    ) -> WorkflowRun:
        return controller.get_run(run_id)

    @router.get(
        "/runs/{run_id}/nodes/{node_id}",
        response_model=RunNodeState,
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="현재 모듈의 Input·Config·Output DTO 상세 조회",
        description=(
            "전체 실행 폴링 응답을 키우지 않고 설정 패널에서 선택한 한 노드의 "
            "현재 Input DTO, Config DTO, Output DTO를 지연 조회합니다."
        ),
    )
    def get_run_node(
        run_id: str = FastPath(..., description="조회할 실행 ID"),
        node_id: str = FastPath(..., description="조회할 노드 ID"),
    ) -> RunNodeState:
        return controller.get_run_node(run_id, node_id)

    @router.post(
        "/runs/{run_id}/resume",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="실패/중단된 워크플로 재개 실행",
        description="실패한 노드부터 이어서 워크플로를 다시 큐에 등록하여 재시도합니다.",
    )
    def resume_run(
        run_id: str = FastPath(..., description="재개할 실행 ID"),
    ) -> WorkflowRun:
        return controller.resume_run(run_id)

    @router.post(
        "/runs/{run_id}/cancel",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="실행 중인 워크플로 취소",
        description="진행 중인 Kubernetes 워커의 워크플로 실행을 중단하고 상태를 `cancelled`로 변경합니다.",
    )
    def cancel_run(
        run_id: str = FastPath(..., description="취소할 실행 ID"),
    ) -> WorkflowRun:
        return controller.cancel_run(run_id)

    @router.get(
        "/runs/{run_id}/stream",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="Server-Sent Events (SSE) 실시간 실행 텔레메트리 스트리밍",
        description=(
            "Kubernetes 워커가 노드를 실행할 때 발생하는 진행 상황(progress), "
            "노드 완료/실패 이벤트, 최종 결과 스냅샷을 브라우저에 실시간 SSE 이벤트로 푸시합니다."
        ),
    )
    async def stream_workflow_run(
        request: Request,
        run_id: str = FastPath(..., description="스트리밍을 구독할 실행 ID"),
    ) -> EventSourceResponse:
        return await controller.stream_run(run_id, request)

    return router


__all__ = [
    "RunListResponse",
    "WorkflowDeleteResponse",
    "WorkflowListResponse",
    "create_workflow_router",
]
