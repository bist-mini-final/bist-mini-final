from __future__ import annotations

import logging
import os
import socket
from datetime import UTC, datetime
from uuid import uuid4

from backend.bootstrap.container import RuntimeContainer
from backend.engine.worker.lease import (
    LeaseHeartbeat,
    terminate_process_on_lease_loss,
)

from .composition import create_bi_materialization_runner
from .database_schema import ensure_bi_schema
from .postgres_store import PostgresBiStore

logger = logging.getLogger(__name__)


def _run(container: RuntimeContainer) -> int:
    completion_client = container.completion_client
    registry = container.services.module_registry
    database_url = registry.db_manager.database_url
    ensure_bi_schema(database_url)
    store = PostgresBiStore(database_url)
    worker_id = (
        os.getenv("KUBERNETES_JOB_NAME")
        or f"{socket.gethostname()}-{uuid4().hex[:12]}"
    )
    claimed = store.claim_next_materialization(worker_id, datetime.now(UTC))
    if claimed is None:
        print("BI materialization queue empty")
        return 0

    heartbeat = LeaseHeartbeat(
        lambda: store.heartbeat_materialization(claimed.job.job_id, worker_id),
        interval_seconds=30,
        thread_name=f"bi-materialization-heartbeat-{claimed.job.job_id}",
        logger=logger,
        failure_message=(
            f"BI materialization heartbeat failed (job_id={claimed.job.job_id})"
        ),
        on_lease_lost=terminate_process_on_lease_loss,
    )
    heartbeat.start()
    try:
        outcome = create_bi_materialization_runner(
            registry,
            completion_client,
        ).materialize(claimed.request, claimed.job.job_id)
        heartbeat.raise_if_lost()
    except Exception as error:
        logger.exception(
            "BI materialization worker failed (job_id=%s)",
            claimed.job.job_id,
        )
        store.fail_claim(
            claimed.job.job_id,
            worker_id,
            datetime.now(UTC),
            str(error) or type(error).__name__,
        )
        return 1
    finally:
        heartbeat.stop()

    print(
        f"BI materialization {outcome.job.job_id} "
        f"finished with {outcome.job.status.value}"
    )
    return 0


def main() -> int:
    with RuntimeContainer.create(require_database=True) as container:
        return _run(container)


if __name__ == "__main__":
    raise SystemExit(main())
