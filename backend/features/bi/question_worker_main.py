import os
import socket
from uuid import uuid4

from backend.bootstrap.container import RuntimeContainer

from .composition import create_bi_question_worker
from .database_schema import ensure_bi_schema
from .question_records import WorkflowRunId


def _run(container: RuntimeContainer) -> int:
    completion_client = container.completion_client
    registry = container.services.module_registry
    ensure_bi_schema(registry.db_manager.database_url)
    worker = create_bi_question_worker(
        registry,
        completion_client,
    )
    kubernetes_job_name = os.getenv("KUBERNETES_JOB_NAME")
    worker_id = WorkflowRunId(
        kubernetes_job_name
        or f"{socket.gethostname()}-{uuid4().hex[:12]}"
    )
    completed = worker.run_one(worker_id)
    if completed is None:
        print("BI question queue empty")
    else:
        print(
            f"BI question {completed.question_id} "
            f"finished with {completed.status.value}"
        )
    return 0


def main() -> int:
    with RuntimeContainer.create(require_database=True) as container:
        return _run(container)


if __name__ == "__main__":
    raise SystemExit(main())
