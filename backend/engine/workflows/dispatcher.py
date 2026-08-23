"""Scheduling boundary for durable workflow runs."""

from __future__ import annotations

from typing import Collection, Optional, Protocol

from .models import WorkflowRun


class RunDispatcher(Protocol):
    """Control-plane contract implemented by the PostgreSQL/Kubernetes queue."""

    def submit(self, run_id: str, *, resume_failed: bool = False) -> bool: ...

    def cancel(self, run_id: str) -> WorkflowRun: ...

    def cancel_all(self) -> int: ...

    def recover_pending(
        self,
        workflow_ids: Optional[Collection[str]] = None,
    ) -> int: ...

    def is_active(self, run_id: str) -> bool: ...

    def shutdown(self) -> None: ...


__all__ = ["RunDispatcher"]
