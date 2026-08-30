"""BI question batch worker entry point.

Each Kubernetes Job pod claims *BI_QUESTION_BATCH_SIZE* questions (default: 16)
and processes them in parallel threads (up to *BI_QUESTION_MAX_WORKERS*, default: 8),
reducing the number of embedding API calls and increasing LLM throughput significantly.
"""

import os

from backend.bootstrap.container import RuntimeContainer
from backend.engine.worker.base import default_worker_id

from .composition import create_bi_question_batch_worker
from .database_schema import ensure_bi_schema
from .question_batch_worker import DEFAULT_BATCH_SIZE, DEFAULT_MAX_WORKERS
from .question_records import WorkflowRunId


def _run(container: RuntimeContainer) -> int:
    completion_client = container.completion_client
    registry = container.services.module_registry
    ensure_bi_schema(registry.db_manager.database_url)

    batch_size = int(os.getenv("BI_QUESTION_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))
    max_workers = int(os.getenv("BI_QUESTION_MAX_WORKERS", str(DEFAULT_MAX_WORKERS)))

    worker = create_bi_question_batch_worker(
        registry,
        completion_client,
        batch_size=batch_size,
        max_workers=max_workers,
    )
    worker_id = WorkflowRunId(default_worker_id())
    saved = worker.run_batch(worker_id)
    if not saved:
        print("BI question queue empty")
    else:
        statuses = ", ".join(q.status.value for q in saved)
        print(f"BI question batch of {len(saved)} finished [{statuses}]")
    return 0


def main() -> int:
    with RuntimeContainer.create(require_database=True) as container:
        return _run(container)


if __name__ == "__main__":
    raise SystemExit(main())
