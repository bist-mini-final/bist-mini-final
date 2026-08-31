"""Read-only operations queries."""

from backend.domains.operations.domain import KubernetesWorkloadSnapshot

from .ports import WorkloadSnapshotReader


class OperationsQueryService:
    def __init__(self, workloads: WorkloadSnapshotReader) -> None:
        self._workloads = workloads

    def workload_snapshot(self) -> KubernetesWorkloadSnapshot:
        return self._workloads.snapshot()


__all__ = ["OperationsQueryService"]
