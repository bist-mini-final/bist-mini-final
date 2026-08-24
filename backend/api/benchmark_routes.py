"""HTTP adapter for benchmark job submission, lifecycle control, and inspection."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi import Path as FastPath
from pydantic import BaseModel, Field

from backend.core.settings import PGVECTOR_URL
from backend.engine.workflows import RunDispatcher, WorkflowExecutor, WorkflowStore
from backend.features.benchmark.postgres_store import (
    BenchmarkPostgresStore,
    BenchmarkStoreError,
)
from backend.features.benchmark.service import (
    BENCHMARK_SET_DIR,
    BENCHMARK_SET_NAMES,
    BenchmarkCase,
    BenchmarkRequest,
    run_snapshot,
    validate_workflows,
)


class BenchmarkJobCreateResponse(BaseModel):
    """벤치마크 작업 큐 등록 성공 응답 DTO."""

    id: str = Field(..., description="등록된 벤치마크 작업 식별자")


class BenchmarkJobStatusResponse(BaseModel):
    """벤치마크 작업 상태 및 진행률 응답 DTO."""

    id: str = Field(..., description="벤치마크 작업 ID")
    status: str = Field(..., description="작업 상태 (queued, running, paused, completed, cancelled, failed)")


def create_benchmark_router(
    workflow_store: WorkflowStore,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
) -> APIRouter:
    """RAG 벤치마크 실행, 제어 및 채점을 위한 FastAPI 라우터 생성."""
    router = APIRouter(tags=["벤치마크 실행 및 채점"])
    database = workflow_executor.run_store.db_manager
    database_url = (
        database.database_url
        if database is not None and hasattr(database, "database_url")
        else PGVECTOR_URL
    )
    benchmark_store = BenchmarkPostgresStore(database_url)

    def load_job(job_id: str) -> Dict[str, Any]:
        try:
            job = benchmark_store.get(job_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if job is None:
            raise HTTPException(status_code=404, detail="벤치마크 작업을 찾을 수 없습니다.")
        return job

    def public_job(job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job)
        active_run_id = payload.pop("active_run_id", None)
        if active_run_id:
            try:
                run = workflow_executor.run_store.load_summary(str(active_run_id))
                payload["active_run"] = run_snapshot(run)
            except (FileNotFoundError, PermissionError, OSError, ValueError):
                payload["active_run"] = None
        else:
            payload["active_run"] = None
        return payload

    @router.get(
        "/benchmark-sets",
        summary="내장 벤치마크 평가 세트 목록 조회",
        description="시스템에 사전 정의된 골든 데이터셋 및 평가 케이스(Benchmark Sets) 목록을 조회합니다.",
    )
    def list_benchmark_sets() -> Dict[str, Any]:
        """내장된 벤치마크 평가 세트 목록을 반환합니다."""
        sets = []
        for path in sorted(BENCHMARK_SET_DIR.glob("*.json")):
            try:
                raw_cases = json.loads(path.read_text(encoding="utf-8"))
                cases = [BenchmarkCase.model_validate(item) for item in raw_cases]
            except (OSError, ValueError, TypeError) as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"올바르지 않은 벤치마크 세트 파일 ({path.name}): {error}",
                ) from error
            sets.append({
                "id": path.stem,
                "name": BENCHMARK_SET_NAMES.get(path.stem, path.stem),
                "cases": [case.model_dump(mode="json", exclude_none=True) for case in cases],
            })
        return {"benchmark_sets": sets}

    @router.post(
        "/benchmarks/jobs",
        status_code=202,
        response_model=BenchmarkJobCreateResponse,
        summary="Kubernetes 벤치마크 평가 작업 큐 등록",
        description=(
            "선택한 워크플로 DAG들과 벤치마크 평가 케이스들을 매핑하여 "
            "PostgreSQL `benchmark_runs` 큐에 등록하고 KEDA 워커가 처리하도록 예약합니다."
        ),
    )
    def start_benchmark_job(request: BenchmarkRequest) -> Dict[str, Any]:
        """벤치마크 평가 작업을 등록하고 큐 ID를 반환합니다."""
        if database is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "BENCHMARK_QUEUE_UNAVAILABLE",
                    "message": "Benchmark 제출에는 PostgreSQL 연결이 필요합니다",
                    "retryable": True,
                    "context": {},
                },
            )
        try:
            validate_workflows(request, workflow_store)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        job_id = f"benchmark-job-{uuid4().hex}"
        try:
            job = benchmark_store.enqueue(
                job_id,
                request.model_dump(mode="json"),
                len(request.cases) * len(request.workflow_ids),
                datetime.now(UTC),
            )
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {"id": job["id"]}

    @router.get(
        "/benchmarks/jobs/{job_id}",
        summary="벤치마크 작업 진행 상태 및 결과 조회",
        description="실행 중이거나 완료된 벤치마크 작업의 진행률, 활성 실행 ID, 완료 통계를 조회합니다.",
    )
    def get_benchmark_job(
        job_id: str = FastPath(..., description="벤치마크 작업 고유 식별자"),
    ) -> Dict[str, Any]:
        """진행 중이거나 완료된 벤치마크 작업의 실시간 상태를 조회합니다."""
        return public_job(load_job(job_id))

    @router.delete(
        "/benchmarks/jobs/{job_id}",
        summary="벤치마크 작업 취소",
        description="실행 대기 중이거나 진행 중인 벤치마크 작업을 즉시 취소하고 활성 파이프라인을 중단합니다.",
    )
    def cancel_benchmark_job(
        job_id: str = FastPath(..., description="취소할 벤치마크 작업 ID"),
    ) -> Dict[str, Any]:
        """실행 중인 벤치마크 작업을 취소합니다."""
        existing = load_job(job_id)
        if existing["status"] in {"completed", "cancelled", "failed"}:
            raise HTTPException(status_code=409, detail="이미 완료되었거나 취소된 벤치마크 작업입니다.")
        try:
            job = benchmark_store.request_cancel(job_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if job is None:
            raise HTTPException(status_code=409, detail="벤치마크 작업을 취소할 수 없습니다.")
        run_id = existing.get("active_run_id")
        if run_id:
            workflow_dispatcher.cancel(str(run_id))
        return {"id": job_id, "status": job["status"]}

    @router.post(
        "/benchmarks/jobs/{job_id}/pause",
        response_model=BenchmarkJobStatusResponse,
        summary="벤치마크 작업 일시 정지",
        description="진행 중인 벤치마크 작업의 다음 케이스 실행을 일시 중지합니다.",
    )
    def pause_benchmark_job(
        job_id: str = FastPath(..., description="일시 정지할 벤치마크 작업 ID"),
    ) -> Dict[str, Any]:
        """진행 중인 벤치마크 작업을 일시 정지합니다."""
        load_job(job_id)
        try:
            job = benchmark_store.request_pause(job_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if job is None:
            raise HTTPException(status_code=409, detail="벤치마크 작업을 일시 정지할 수 없습니다.")
        return {"id": job_id, "status": job["status"]}

    @router.post(
        "/benchmarks/jobs/{job_id}/resume",
        response_model=BenchmarkJobStatusResponse,
        summary="벤치마크 작업 재개",
        description="일시 정지된 벤치마크 작업의 평가를 다시 시작합니다.",
    )
    def resume_benchmark_job(
        job_id: str = FastPath(..., description="재개할 벤치마크 작업 ID"),
    ) -> Dict[str, Any]:
        """일시 정지된 벤치마크 작업을 다시 시작합니다."""
        load_job(job_id)
        try:
            job = benchmark_store.request_resume(job_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if job is None:
            raise HTTPException(status_code=409, detail="일시 정지 상태가 아닌 벤치마크 작업입니다.")
        return {"id": job_id, "status": job["status"]}

    @router.get(
        "/benchmarks",
        summary="완료된 벤치마크 평가 결과 목록 조회",
        description="저장된 전체 벤치마크 평가 실행 결과 및 집계 스코어 목록을 반환합니다.",
    )
    def list_benchmarks() -> Dict[str, Any]:
        """완료된 전체 벤치마크 평가 결과 목록을 반환합니다."""
        try:
            return {"benchmarks": benchmark_store.list_results()}
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get(
        "/benchmarks/{benchmark_id}",
        summary="특정 벤치마크 결과 상세 조회",
        description="단일 벤치마크 실행의 질문별 정답률, 응답 지연, 모듈별 점수 상세 데이터를 조회합니다.",
    )
    def get_benchmark(
        benchmark_id: str = FastPath(..., description="조회할 벤치마크 결과 ID"),
    ) -> Dict[str, Any]:
        """지정된 단일 벤치마크 평가의 상세 채점 결과를 반환합니다."""
        try:
            result = benchmark_store.get_result(benchmark_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if result is None:
            raise HTTPException(status_code=404, detail="벤치마크 결과를 찾을 수 없습니다.")
        return result

    return router
