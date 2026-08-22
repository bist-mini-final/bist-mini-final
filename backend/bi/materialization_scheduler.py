from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .api_services import BiApiServices, BiMaterializationRunnerPort
from .api_state import is_active, job_id_for
from .models import (
    BiCompany,
    BiMaterializationJob,
    BiMaterializationRequest,
    JobId,
    MaterializationStatus,
)


class BiMaterializationSubmitterPort(Protocol):
    def submit(self, request: BiMaterializationRequest, job_id: JobId) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


class BiScheduleStatus(StrEnum):
    SCHEDULED = "scheduled"
    REUSED = "reused"
    BUSY = "busy"


@dataclass(frozen=True, slots=True)
class BiScheduleResult:
    status: BiScheduleStatus
    job: BiMaterializationJob


class BiMaterializationScheduler:
    def __init__(
        self,
        services: BiApiServices,
        submitter: BiMaterializationSubmitterPort,
    ) -> None:
        self._services = services
        self._submitter = submitter

    def schedule(self, request: BiMaterializationRequest) -> BiScheduleResult:
        existing = self._services.store.find_latest_job(
            request.company_id,
            request.source.workbook_hash,
        )
        if existing is not None:
            return BiScheduleResult(BiScheduleStatus.REUSED, existing)

        latest = self._services.store.get_latest_job(request.company_id)
        if latest is not None and is_active(latest.status):
            return BiScheduleResult(BiScheduleStatus.BUSY, latest)

        job_id = job_id_for(request)
        now = self._services.clock.now()
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
        self._services.store.register_company(
            BiCompany(
                company_id=request.company_id,
                display_name=request.display_name,
            )
        )
        self._services.store.save_job(queued)
        self._submitter.submit(request, job_id)
        return BiScheduleResult(BiScheduleStatus.SCHEDULED, queued)

    def shutdown(self, wait: bool = True) -> None:
        self._submitter.shutdown(wait)


class ThreadedBiMaterializationSubmitter:
    def __init__(self, runner: BiMaterializationRunnerPort) -> None:
        self._runner = runner
        self._pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="bi-materialization",
        )

    def submit(self, request: BiMaterializationRequest, job_id: JobId) -> None:
        self._pool.submit(self._runner.materialize, request, job_id)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=True)
