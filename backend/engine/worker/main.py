"""Compatibility entrypoint for the workflow worker."""

from backend.domains.workflow.workers.main import (
    WorkflowWorkerServices,
    execute_with_policy,
    main,
    run_one,
    task_timeout,
)

__all__ = [
    "WorkflowWorkerServices",
    "execute_with_policy",
    "main",
    "run_one",
    "task_timeout",
]
