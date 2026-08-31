"""Benchmark commands and queries independent from HTTP presentation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.domains.benchmark.domain import BenchmarkCase, BenchmarkRequest
from backend.domains.workflow.application.execution_service import WorkflowExecutionPort
from backend.domains.workflow.application.ports import WorkflowDefinitionRepository
from backend.shared.domain import (
    ApplicationConflict,
    ApplicationInternalError,
    ApplicationValidationError,
    ResourceNotFoundError,
    RetryableInfrastructureError,
)

from .execution import run_snapshot, validate_workflows
from .ports import (
    BenchmarkRunStorePort,
    BenchmarkSetSourceError,
    BenchmarkSetSourcePort,
    BenchmarkStoreError,
    BenchmarkStorePort,
)


class BenchmarkNotFoundError(ResourceNotFoundError):
    code = "HTTP_404"


class BenchmarkConflictError(ApplicationConflict):
    code = "HTTP_409"


class BenchmarkValidationError(ApplicationValidationError):
    code = "HTTP_422"


class BenchmarkSetError(ApplicationInternalError):
    code = "HTTP_500"


class BenchmarkUnavailableError(RetryableInfrastructureError):
    code = "HTTP_503"


class BenchmarkQueueUnavailableError(BenchmarkUnavailableError):
    code = "BENCHMARK_QUEUE_UNAVAILABLE"


class BenchmarkApplicationService:
    """Coordinate benchmark validation, durable queueing, control, and inspection."""

    def __init__(
        self,
        *,
        store: BenchmarkStorePort,
        workflow_store: WorkflowDefinitionRepository,
        run_store: BenchmarkRunStorePort,
        workflow_execution: WorkflowExecutionPort,
        benchmark_sets: BenchmarkSetSourcePort,
        queue_available: bool,
    ) -> None:
        self._store = store
        self._workflow_store = workflow_store
        self._run_store = run_store
        self._workflow_execution = workflow_execution
        self._benchmark_sets = benchmark_sets
        self._queue_available = queue_available

    def list_benchmark_sets(self) -> dict[str, Any]:
        sets: list[dict[str, Any]] = []
        try:
            documents = self._benchmark_sets.list_documents()
        except BenchmarkSetSourceError as error:
            raise BenchmarkSetError(str(error)) from error
        for document in documents:
            try:
                cases = [BenchmarkCase.model_validate(item) for item in document.cases]
            except (ValueError, TypeError) as error:
                raise BenchmarkSetError(
                    f"올바르지 않은 벤치마크 세트 ({document.set_id}): {error}"
                ) from error
            sets.append(
                {
                    "id": document.set_id,
                    "name": document.name,
                    "cases": [case.model_dump(mode="json", exclude_none=True) for case in cases],
                }
            )
        return {"benchmark_sets": sets}

    def start_job(self, request: BenchmarkRequest) -> dict[str, str]:
        if not self._queue_available:
            raise BenchmarkQueueUnavailableError(
                "Benchmark 제출에는 PostgreSQL 연결이 필요합니다"
            )
        try:
            validate_workflows(request, self._workflow_store)
        except FileNotFoundError as error:
            raise BenchmarkNotFoundError(str(error)) from error
        except ValueError as error:
            raise BenchmarkValidationError(str(error)) from error

        job_id = f"benchmark-job-{uuid4().hex}"
        try:
            job = self._store.enqueue(
                job_id,
                request.model_dump(mode="json"),
                len(request.cases) * len(request.workflow_ids),
                datetime.now(UTC),
            )
        except BenchmarkStoreError as error:
            raise BenchmarkUnavailableError(str(error)) from error
        return {"id": str(job["id"])}

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._public_job(self._load_job(job_id))

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        existing = self._load_job(job_id)
        if existing["status"] in {"completed", "cancelled", "failed"}:
            raise BenchmarkConflictError(
                "이미 완료, 취소 또는 실패한 벤치마크 작업입니다."
            )
        job = self._control_job(job_id, "cancel")
        run_id = existing.get("active_run_id")
        if run_id:
            self._workflow_execution.cancel(str(run_id))
        return {"id": job_id, "status": job["status"]}

    def pause_job(self, job_id: str) -> dict[str, Any]:
        self._load_job(job_id)
        job = self._control_job(job_id, "pause")
        return {"id": job_id, "status": job["status"]}

    def resume_job(self, job_id: str) -> dict[str, Any]:
        self._load_job(job_id)
        job = self._control_job(job_id, "resume")
        return {"id": job_id, "status": job["status"]}

    def list_results(self) -> dict[str, Any]:
        try:
            return {"benchmarks": self._store.list_results()}
        except BenchmarkStoreError as error:
            raise BenchmarkUnavailableError(str(error)) from error

    def get_result(self, benchmark_id: str) -> dict[str, Any]:
        try:
            result = self._store.get_result(benchmark_id)
        except BenchmarkStoreError as error:
            raise BenchmarkUnavailableError(str(error)) from error
        if result is None:
            raise BenchmarkNotFoundError("벤치마크 결과를 찾을 수 없습니다.")
        return result

    def _load_job(self, job_id: str) -> dict[str, Any]:
        try:
            job = self._store.get(job_id)
        except BenchmarkStoreError as error:
            raise BenchmarkUnavailableError(str(error)) from error
        if job is None:
            raise BenchmarkNotFoundError("벤치마크 작업을 찾을 수 없습니다.")
        return job

    def _public_job(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job)
        active_run_id = payload.pop("active_run_id", None)
        if not active_run_id:
            payload["active_run"] = None
            return payload
        try:
            run = self._run_store.load_summary(str(active_run_id))
            payload["active_run"] = run_snapshot(run)
        except (FileNotFoundError, PermissionError, OSError, ValueError):
            payload["active_run"] = None
        return payload

    def _control_job(self, job_id: str, action: str) -> dict[str, Any]:
        operations = {
            "cancel": self._store.request_cancel,
            "pause": self._store.request_pause,
            "resume": self._store.request_resume,
        }
        try:
            job = operations[action](job_id)
        except BenchmarkStoreError as error:
            raise BenchmarkUnavailableError(str(error)) from error
        if job is not None:
            return job
        messages = {
            "cancel": "벤치마크 작업을 취소할 수 없습니다.",
            "pause": "벤치마크 작업을 일시 정지할 수 없습니다.",
            "resume": "일시 정지 상태가 아닌 벤치마크 작업입니다.",
        }
        raise BenchmarkConflictError(messages[action])


__all__ = [
    "BenchmarkApplicationService",
    "BenchmarkConflictError",
    "BenchmarkNotFoundError",
    "BenchmarkQueueUnavailableError",
    "BenchmarkSetError",
    "BenchmarkStorePort",
    "BenchmarkUnavailableError",
    "BenchmarkValidationError",
]
