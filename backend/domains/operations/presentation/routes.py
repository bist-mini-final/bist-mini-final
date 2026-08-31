"""Read-only Kubernetes workload monitoring HTTP adapter."""

from fastapi import APIRouter

from backend.domains.operations.application import OperationsQueryService
from backend.domains.operations.domain import KubernetesWorkloadSnapshot


def create_job_router(service: OperationsQueryService) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["Kubernetes 작업 관제"])

    @router.get(
        "",
        response_model=KubernetesWorkloadSnapshot,
        summary="Kubernetes ScaledJob, Job, Pod 상태 조회",
    )
    def list_workloads() -> KubernetesWorkloadSnapshot:
        return service.workload_snapshot()

    return router


__all__ = ["create_job_router"]
