"""HTTP presentation for benchmark submission, lifecycle control, and inspection."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Path as FastPath
from pydantic import BaseModel, Field

from backend.core.settings import PGVECTOR_URL
from backend.domains.benchmark.application import BenchmarkApplicationService
from backend.engine.workflows import RunStore, WorkflowExecutionPort, WorkflowStore
from backend.features.benchmark.postgres_store import BenchmarkPostgresStore
from backend.features.benchmark.service import BenchmarkRequest


class BenchmarkJobCreateResponse(BaseModel):
    """벤치마크 작업 큐 등록 성공 응답 DTO."""

    id: str = Field(..., description="등록된 벤치마크 작업 식별자")


class BenchmarkJobStatusResponse(BaseModel):
    """벤치마크 작업 상태 및 진행률 응답 DTO."""

    id: str = Field(..., description="벤치마크 작업 ID")
    status: str = Field(..., description="작업 상태 (queued, running, paused, completed, cancelled, failed)")


def create_benchmark_router(
    workflow_store: WorkflowStore,
    run_store: RunStore,
    workflow_execution: WorkflowExecutionPort,
) -> APIRouter:
    """Create the benchmark API while keeping HTTP metadata at the edge."""
    router = APIRouter(tags=["벤치마크 실행 및 채점"])
    database = run_store.db_manager
    database_url = (
        database.database_url
        if database is not None and hasattr(database, "database_url")
        else PGVECTOR_URL
    )
    service = BenchmarkApplicationService(
        store=BenchmarkPostgresStore(database_url),
        workflow_store=workflow_store,
        run_store=run_store,
        workflow_execution=workflow_execution,
        queue_available=database is not None,
    )

    @router.get(
        "/benchmark-sets",
        summary="내장 벤치마크 평가 세트 목록 조회",
        description="시스템에 사전 정의된 골든 데이터셋 및 평가 케이스(Benchmark Sets) 목록을 조회합니다.",
    )
    def list_benchmark_sets() -> dict[str, Any]:
        return service.list_benchmark_sets()

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
    def start_benchmark_job(request: BenchmarkRequest) -> dict[str, Any]:
        return service.start_job(request)

    @router.get(
        "/benchmarks/jobs/{job_id}",
        summary="벤치마크 작업 진행 상태 및 결과 조회",
        description="실행 중이거나 완료된 벤치마크 작업의 진행률, 활성 실행 ID, 완료 통계를 조회합니다.",
    )
    def get_benchmark_job(
        job_id: str = FastPath(..., description="벤치마크 작업 고유 식별자"),
    ) -> dict[str, Any]:
        return service.get_job(job_id)

    @router.delete(
        "/benchmarks/jobs/{job_id}",
        summary="벤치마크 작업 취소",
        description="실행 대기 중이거나 진행 중인 벤치마크 작업을 즉시 취소하고 활성 파이프라인을 중단합니다.",
    )
    def cancel_benchmark_job(
        job_id: str = FastPath(..., description="취소할 벤치마크 작업 ID"),
    ) -> dict[str, Any]:
        return service.cancel_job(job_id)

    @router.post(
        "/benchmarks/jobs/{job_id}/pause",
        response_model=BenchmarkJobStatusResponse,
        summary="벤치마크 작업 일시 정지",
        description="진행 중인 벤치마크 작업의 다음 케이스 실행을 일시 중지합니다.",
    )
    def pause_benchmark_job(
        job_id: str = FastPath(..., description="일시 정지할 벤치마크 작업 ID"),
    ) -> dict[str, Any]:
        return service.pause_job(job_id)

    @router.post(
        "/benchmarks/jobs/{job_id}/resume",
        response_model=BenchmarkJobStatusResponse,
        summary="벤치마크 작업 재개",
        description="일시 정지된 벤치마크 작업의 평가를 다시 시작합니다.",
    )
    def resume_benchmark_job(
        job_id: str = FastPath(..., description="재개할 벤치마크 작업 ID"),
    ) -> dict[str, Any]:
        return service.resume_job(job_id)

    @router.get(
        "/benchmarks",
        summary="완료된 벤치마크 평가 결과 목록 조회",
        description="저장된 전체 벤치마크 평가 실행 결과 및 집계 스코어 목록을 반환합니다.",
    )
    def list_benchmarks() -> dict[str, Any]:
        return service.list_results()

    @router.get(
        "/benchmarks/{benchmark_id}",
        summary="특정 벤치마크 결과 상세 조회",
        description="단일 벤치마크 실행의 질문별 정답률, 응답 지연, 모듈별 점수 상세 데이터를 조회합니다.",
    )
    def get_benchmark(
        benchmark_id: str = FastPath(..., description="조회할 벤치마크 결과 ID"),
    ) -> dict[str, Any]:
        return service.get_result(benchmark_id)

    return router


__all__ = ["create_benchmark_router"]
