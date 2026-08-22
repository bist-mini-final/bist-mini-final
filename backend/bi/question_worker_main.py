import os
import socket
from uuid import uuid4

from backend.core.settings import CACHE_DIR
from backend.llm.chat_completion import ChatCompletionClient
from backend.runtime.registry import ModuleRegistry
from backend.storage.answer_cache import AnswerCacheRepository

from .composition import create_bi_question_worker
from .question_records import WorkflowRunId


def main() -> int:
    completion_client = ChatCompletionClient()
    registry = ModuleRegistry(
        AnswerCacheRepository(CACHE_DIR / "bi-question-worker.json"),
        completion_client=completion_client,
    )
    worker = create_bi_question_worker(registry, completion_client)
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


if __name__ == "__main__":
    raise SystemExit(main())
