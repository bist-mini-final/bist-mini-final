"""Read ports consumed by the operations workload projection."""

from __future__ import annotations

from typing import Any, Protocol

from backend.domains.operations.domain import KubernetesWorkloadSnapshot


class WorkflowLeaseReader(Protocol):
    def list_active_workflow_leases(
        self,
        *,
        stale_after_seconds: int = 180,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...


class WorkloadSnapshotReader(Protocol):
    def snapshot(self) -> KubernetesWorkloadSnapshot: ...


__all__ = ["WorkflowLeaseReader", "WorkloadSnapshotReader"]
