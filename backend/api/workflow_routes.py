"""HTTP and SSE streaming API endpoints for DAG workflow definitions and Kubernetes batch runs."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as FastPath
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.core.state_stream import SharedStateStream
from backend.engine.workflows import (
    ActiveWorkflowRunsError,
    DagExecutionError,
    RunStore,
    WorkflowExecutionPort,
    WorkflowExecutionRequest,
    WorkflowSaveRequest,
    WorkflowStore,
)


class WorkflowListResponse(BaseModel):
    """저장된 전체 DAG 워크플로 정의 목록 응답 DTO."""

    workflows: List[Dict[str, Any]] = Field(..., description="저장된 전체 DAG 워크플로 목록")


class WorkflowDeleteResponse(BaseModel):
    """워크플로 삭제 성공 응답 DTO."""

    deleted: str = Field(..., description="삭제된 워크플로 ID")


class RunListResponse(BaseModel):
    """워크플로 실행 요약 기록 목록 응답 DTO."""

    runs: List[Dict[str, Any]] = Field(..., description="워크플로 실행 기록 목록")


def create_workflow_router(
    *,
    workflow_store: WorkflowStore,
    run_store: RunStore,
    workflow_execution: WorkflowExecutionPort,
) -> APIRouter:
    """DAG 워크플로 저장소, 노드 실행 및 실시간 SSE 텔레메트리 스트리밍을 위한 FastAPI 라우터 생성."""
    router = APIRouter()
    run_stream = SharedStateStream(
        run_store.load_summary,
        fingerprint=lambda run: run.updated_at,
        terminal=lambda run: run.status in ("completed", "failed", "paused"),
    )

    @router.delete(
        "/cache",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="런타임 캐시 및 실행 아티팩트 전체 초기화",
        description="실행 중인 워크플로가 없을 때 임베딩, 검색 결과, 임시 파일 캐시를 모두 삭제합니다.",
    )
    def clear_runtime_cache() -> Dict[str, Any]:
        """실행 중인 워크플로가 없을 때 메모리 및 디스크의 런타임 캐시를 초기화합니다."""
        try:
            return workflow_execution.clear_runtime_cache()
        except ActiveWorkflowRunsError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            ) from error

    @router.get(
        "/workflows",
        tags=["워크플로 정의 관리"],
        response_model=WorkflowListResponse,
        summary="저장된 DAG 워크플로 목록 조회",
        description="시스템에 저장된 모든 RAG/시계열 파이프라인 DAG 워크플로 정의 목록을 반환합니다.",
    )
    def list_workflows() -> Dict[str, Any]:
        """저장된 전체 DAG 워크플로 정의 목록을 반환합니다."""
        return {"workflows": workflow_store.list()}

    @router.get(
        "/workflows/{workflow_id}",
        tags=["워크플로 정의 관리"],
        summary="단일 DAG 워크플로 상세 정의 조회",
        description="지정된 `workflow_id`의 노드(Node), 엣지(Edge), 모듈 설정 및 뷰포트 상태를 조회합니다.",
    )
    def get_workflow(
        workflow_id: str = FastPath(..., description="조회할 워크플로 식별자"),
    ) -> Any:
        """지정된 식별자의 워크플로 상세 정의를 반환합니다."""
        try:
            return workflow_store.load(workflow_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"워크플로 {workflow_id}를 찾을 수 없습니다."
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.put(
        "/workflows/{workflow_id}",
        tags=["워크플로 정의 관리"],
        summary="DAG 워크플로 생성 또는 업데이트 저장",
        description="XYFlow 캔버스에서 편집된 노드 연결 및 모듈 설정을 워크플로 저장소에 영속화합니다.",
    )
    def save_workflow(
        workflow_id: str = FastPath(..., description="저장할 워크플로 식별자"),
        request: WorkflowSaveRequest = None,  # type: ignore[assignment]
    ) -> Any:
        """DAG 워크플로 정의를 새로 생성하거나 업데이트합니다."""
        if request is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        try:
            return workflow_store.save(workflow_id, request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.delete(
        "/workflows/{workflow_id}",
        tags=["워크플로 정의 관리"],
        response_model=WorkflowDeleteResponse,
        summary="DAG 워크플로 삭제",
        description="저장소에서 해당 워크플로 정의를 영구 삭제합니다.",
    )
    def delete_workflow(
        workflow_id: str = FastPath(..., description="삭제할 워크플로 식별자"),
    ) -> Dict[str, Any]:
        """저장소에서 지정된 워크플로 정의를 삭제합니다."""
        try:
            workflow_store.delete(workflow_id)
            return {"deleted": workflow_id}
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"워크플로를 찾을 수 없습니다: {workflow_id}") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
    ) -> Any:
        """새로운 워크플로 실행 작업을 큐에 등록합니다."""
        if request is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        try:
            return workflow_execution.submit(workflow_id, request)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"워크플로 {workflow_id}를 찾을 수 없습니다."
            ) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"workflow_id": workflow_id},
                },
            ) from error

    @router.get(
        "/runs",
        tags=["워크플로 실행 및 실시간 스트림"],
        response_model=RunListResponse,
        summary="워크플로 실행 기록 목록 조회",
        description="전체 또는 특정 워크플로의 이전 실행 상태, 소요 시간, 노드 성공/실패 기록을 조회합니다.",
    )
    def list_runs(
        workflow_id: Optional[str] = Query(default=None, description="특정 워크플로 필터링 ID"),
        limit: int = Query(default=50, ge=1, le=200, description="반환할 최대 실행 수"),
    ) -> Dict[str, Any]:
        """과거 워크플로 실행 기록 및 요약 상태 목록을 반환합니다."""
        return {"runs": run_store.list(workflow_id, limit)}

    @router.get(
        "/runs/{run_id}",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="단일 워크플로 실행 상태 및 노드 결과 상세 조회",
        description="지정된 실행(`run_id`)의 실시간 상태, 각 노드별 입력/출력 데이터, 토큰 비용, 지연 시간을 반환합니다.",
    )
    def get_run(
        run_id: str = FastPath(..., description="조회할 실행 ID"),
    ) -> Any:
        """워크플로 실행의 전체 상태 스냅샷 및 노드별 실행 결과를 반환합니다."""
        try:
            return run_store.load_summary(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다."
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post(
        "/runs/{run_id}/resume",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="실패/중단된 워크플로 재개 실행",
        description="실패한 노드부터 이어서 워크플로를 다시 큐에 등록하여 재시도합니다.",
    )
    def resume_run(
        run_id: str = FastPath(..., description="재개할 실행 ID"),
    ) -> Any:
        """실패하거나 일시 중지된 워크플로 실행을 재개합니다."""
        try:
            return workflow_execution.resume(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다."
            ) from error
        except DagExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"run_id": run_id},
                },
            ) from error

    @router.post(
        "/runs/{run_id}/cancel",
        tags=["워크플로 실행 및 실시간 스트림"],
        summary="실행 중인 워크플로 취소",
        description="진행 중인 Kubernetes 워커의 워크플로 실행을 중단하고 상태를 `cancelled`로 변경합니다.",
    )
    def cancel_run(
        run_id: str = FastPath(..., description="취소할 실행 ID"),
    ) -> Any:
        """진행 중인 워크플로 실행을 즉시 취소합니다."""
        try:
            return workflow_execution.cancel(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다."
            ) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"run_id": run_id},
                },
            ) from error

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
        run_id: str = FastPath(..., description="스트리밍을 구독할 실행 ID"),
        request: Request = None,  # type: ignore[assignment]
    ) -> EventSourceResponse:
        """실행 중인 워크플로의 노드 상태 변경 및 텔레메트리를 실시간 스트리밍합니다."""
        try:
            initial_run = await to_thread.run_sync(run_store.load_summary, run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다."
            ) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"run_id": run_id},
                },
            ) from error

        async def event_generator():
            previous_node_statuses: dict[str, tuple[object, ...]] = {}
            started = False
            try:
                async for run in run_stream.subscribe(run_id, initial=initial_run):
                    if await request.is_disconnected():
                        break
                    if not started:
                        started = True
                        yield {
                            "event": "run_started",
                            "data": json.dumps(
                                {
                                    "run_id": run.id,
                                    "workflow_id": run.workflow_id,
                                    "status": run.status,
                                    "batches_count": len(run.batches),
                                    "nodes_count": len(run.nodes),
                                },
                                ensure_ascii=False,
                            ),
                        }
                    for node_id, node in run.nodes.items():
                        fingerprint = (
                            node.status,
                            node.elapsed_ms,
                            node.error,
                            json.dumps(node.progress, sort_keys=True, default=str),
                        )
                        if previous_node_statuses.get(node_id) == fingerprint:
                            continue
                        previous_node_statuses[node_id] = fingerprint
                        yield {
                            "event": (
                                "node_completed"
                                if node.status in ("succeeded", "skipped")
                                else "node_failed"
                                if node.status == "failed"
                                else "node_started"
                                if node.status == "running"
                                else "node_progress"
                            ),
                            "data": json.dumps(
                                node.model_dump(mode="json"),
                                ensure_ascii=False,
                            ),
                        }
                    if run.status in ("completed", "failed", "paused"):
                        yield {
                            "event": (
                                "run_finished"
                                if run.status == "completed"
                                else "run_failed"
                            ),
                            "data": json.dumps(
                                {
                                    "run_id": run.id,
                                    "status": run.status,
                                    "run": run.model_dump(mode="json"),
                                },
                                ensure_ascii=False,
                            ),
                        }
                        break
            except Exception as error:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(error), "run_id": run_id}, ensure_ascii=False),
                }

        return EventSourceResponse(event_generator(), ping=15)

    return router
