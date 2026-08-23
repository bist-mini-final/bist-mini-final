"""HTTP adapter for benchmark job submission and inspection."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, HTTPException

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


def create_benchmark_router(
    workflow_store: WorkflowStore,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
) -> APIRouter:
    router = APIRouter()
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
            raise HTTPException(status_code=404, detail="Benchmark job not found")
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

    @router.get("/benchmark-sets")
    def list_benchmark_sets():
        """Return checked-in benchmark cases validated against the live schema."""

        sets = []
        for path in sorted(BENCHMARK_SET_DIR.glob("*.json")):
            try:
                raw_cases = json.loads(path.read_text(encoding="utf-8"))
                cases = [BenchmarkCase.model_validate(item) for item in raw_cases]
            except (OSError, ValueError, TypeError) as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Invalid benchmark set {path.name}: {error}",
                ) from error
            sets.append({
                "id": path.stem,
                "name": BENCHMARK_SET_NAMES.get(path.stem, path.stem),
                "cases": [case.model_dump(mode="json", exclude_none=True) for case in cases],
            })
        return {"benchmark_sets": sets}

    @router.post("/benchmarks/jobs", status_code=202)
    def start_benchmark_job(request: BenchmarkRequest):
        """Persist a comparison for the benchmark Kubernetes queue."""
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

    @router.get("/benchmarks/jobs/{job_id}")
    def get_benchmark_job(job_id: str):
        return public_job(load_job(job_id))

    @router.delete("/benchmarks/jobs/{job_id}")
    def cancel_benchmark_job(job_id: str):
        existing = load_job(job_id)
        if existing["status"] in {"completed", "cancelled", "failed"}:
            raise HTTPException(status_code=409, detail="Benchmark job cannot be cancelled")
        try:
            job = benchmark_store.request_cancel(job_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if job is None:
            raise HTTPException(status_code=409, detail="Benchmark job cannot be cancelled")
        run_id = existing.get("active_run_id")
        if run_id:
            workflow_dispatcher.cancel(str(run_id))
        return {"id": job_id, "status": job["status"]}

    @router.post("/benchmarks/jobs/{job_id}/pause")
    def pause_benchmark_job(job_id: str):
        load_job(job_id)
        try:
            job = benchmark_store.request_pause(job_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if job is None:
            raise HTTPException(status_code=409, detail="Benchmark job cannot be paused")
        return {"id": job_id, "status": job["status"]}

    @router.post("/benchmarks/jobs/{job_id}/resume")
    def resume_benchmark_job(job_id: str):
        load_job(job_id)
        try:
            job = benchmark_store.request_resume(job_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if job is None:
            raise HTTPException(status_code=409, detail="Benchmark job is not paused")
        return {"id": job_id, "status": job["status"]}

    @router.get("/benchmarks")
    def list_benchmarks():
        try:
            return {"benchmarks": benchmark_store.list_results()}
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get("/benchmarks/{benchmark_id}")
    def get_benchmark(benchmark_id: str):
        try:
            result = benchmark_store.get_result(benchmark_id)
        except BenchmarkStoreError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if result is None:
            raise HTTPException(status_code=404, detail="Benchmark result not found")
        return result

    return router
