"""Read-only Kubernetes workload monitoring HTTP adapter."""

from fastapi import APIRouter

from backend.features.job_monitoring import KubernetesWorkloadSnapshot
from backend.providers.kubernetes_monitor import KubernetesMonitor


def create_job_router(monitor: KubernetesMonitor) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["Kubernetes 작업 관제"])

    @router.get(
        "",
        response_model=KubernetesWorkloadSnapshot,
        summary="Kubernetes ScaledJob, Job, Pod 상태 조회",
    )
    def list_workloads() -> KubernetesWorkloadSnapshot:
        return monitor.snapshot()

    return router


__all__ = ["create_job_router"]
