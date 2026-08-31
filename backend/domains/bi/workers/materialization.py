"""BI materialization worker process adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol

from backend.domains.bi.application.materializer import (
    BiMaterializationRunnerPort,
    ClaimedBiMaterialization,
)
from backend.domains.bi.domain.materialization_models import BiMaterializationOutcome
from backend.domains.bi.domain.models import JobId
from backend.shared.application.workers import (
    LeasedWorker,
    WorkerLeaseSpec,
    default_worker_id,
)

logger = logging.getLogger(__name__)


class BiMaterializationWorkerStorePort(Protocol):
    def claim_next_materialization(
        self,
        worker_id: str,
        claimed_at: datetime,
    ) -> ClaimedBiMaterialization | None: ...

    def heartbeat_materialization(self, job_id: JobId, worker_id: str) -> bool: ...

    def fail_claim(
        self,
        job_id: JobId,
        worker_id: str,
        failed_at: datetime,
        message: str,
    ) -> None: ...


class BiMaterializationWorker(
    LeasedWorker[ClaimedBiMaterialization, BiMaterializationOutcome]
):
    def __init__(
        self,
        store: BiMaterializationWorkerStorePort,
        runner: BiMaterializationRunnerPort,
        worker_id: str,
    ) -> None:
        super().__init__(logger)
        self._store = store
        self._runner = runner
        self._worker_id = worker_id

    def claim(self) -> ClaimedBiMaterialization | None:
        return self._store.claim_next_materialization(
            self._worker_id,
            datetime.now(UTC),
        )

    def lease_spec(self, claim: ClaimedBiMaterialization) -> WorkerLeaseSpec:
        job_id = str(claim.job.job_id)
        return WorkerLeaseSpec(
            job_id=job_id,
            worker_id=self._worker_id,
            renew=lambda: self._store.heartbeat_materialization(
                claim.job.job_id,
                self._worker_id,
            ),
            thread_name=f"bi-materialization-heartbeat-{job_id}",
            failure_message=(
                f"BI materialization heartbeat failed (job_id={job_id})"
            ),
        )

    def execute(
        self,
        claim: ClaimedBiMaterialization,
    ) -> BiMaterializationOutcome:
        return self._runner.materialize(claim.request, claim.job.job_id)

    def complete(
        self,
        claim: ClaimedBiMaterialization,
        output: BiMaterializationOutcome,
        duration_seconds: float,
    ) -> None:
        # The queued materializer atomically persists its own outcome because a
        # successful worker can legitimately publish an unavailable snapshot.
        return None

    def fail(
        self,
        claim: ClaimedBiMaterialization,
        error: Exception,
        duration_seconds: float,
    ) -> None:
        self._store.fail_claim(
            claim.job.job_id,
            self._worker_id,
            datetime.now(UTC),
            str(error) or type(error).__name__,
        )

    def empty_message(self) -> str:
        return "BI materialization queue empty"

    def completed_message(
        self,
        claim: ClaimedBiMaterialization,
        output: BiMaterializationOutcome,
    ) -> str:
        return (
            f"BI materialization {output.job.job_id} "
            f"finished with {output.job.status.value}"
        )

    def failed_message(
        self,
        claim: ClaimedBiMaterialization,
        error: Exception,
    ) -> str:
        return f"BI materialization worker failed (job_id={claim.job.job_id})"


def main(
    *,
    store: BiMaterializationWorkerStorePort,
    runner: BiMaterializationRunnerPort,
    worker_id: str | None = None,
) -> int:
    return BiMaterializationWorker(
        store,
        runner,
        worker_id or default_worker_id(),
    ).run_once()
