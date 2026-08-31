from __future__ import annotations

import logging
from datetime import UTC, datetime

from backend.bootstrap.application import RuntimeContainer
from backend.bootstrap.bi import create_bi_materialization_runner
from backend.domains.bi.domain.materialization_models import BiMaterializationOutcome
from backend.shared.application.workers import (
    LeasedWorker,
    WorkerLeaseSpec,
    default_worker_id,
)

from .database_schema import ensure_bi_schema
from .postgres_store import ClaimedBiMaterialization, PostgresBiStore

logger = logging.getLogger(__name__)


class BiMaterializationWorker(
    LeasedWorker[ClaimedBiMaterialization, BiMaterializationOutcome]
):
    def __init__(
        self,
        container: RuntimeContainer,
        store: PostgresBiStore,
        worker_id: str,
    ) -> None:
        super().__init__(logger)
        self._container = container
        self._store = store
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
        return create_bi_materialization_runner(
            self._container.services.module_registry,
            self._container.completion_client,
        ).materialize(claim.request, claim.job.job_id)

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


def _run(container: RuntimeContainer) -> int:
    database_url = container.services.module_registry.db_manager.database_url
    ensure_bi_schema(database_url)
    return BiMaterializationWorker(
        container,
        PostgresBiStore(database_url),
        default_worker_id(),
    ).run_once()


def main() -> int:
    with RuntimeContainer.create(require_database=True) as container:
        return _run(container)


if __name__ == "__main__":
    raise SystemExit(main())
