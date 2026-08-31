"""Public DTOs for the read-only Kubernetes jobs portal."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KubernetesResourceSummary(BaseModel):
    kind: Literal["ScaledJob", "Job", "Pod"]
    name: str
    namespace: str
    status: str
    ready: bool | None = None
    active: bool | None = None
    succeeded: int | None = Field(default=None, ge=0)
    failed: int | None = Field(default=None, ge=0)
    created_at: datetime | None = None
    message: str | None = None


class WorkflowLeaseSummary(BaseModel):
    run_id: str
    workflow_id: str
    queue_name: str
    status: str
    worker_id: str | None = None
    priority: int
    attempt_count: int = Field(ge=0)
    available_at: datetime
    claimed_at: datetime | None = None
    heartbeat_at: datetime | None = None
    heartbeat_age_seconds: float | None = Field(default=None, ge=0)
    lease_ttl_seconds: float | None = Field(default=None, ge=0)
    lease_stale: bool = False
    cancel_requested: bool = False
    created_at: datetime
    updated_at: datetime
    kubernetes_resource: str | None = None


class KubernetesWorkloadSnapshot(BaseModel):
    available: bool
    source: Literal["in_cluster", "kubectl", "unavailable"]
    namespace: str
    context: str | None = None
    collected_at: datetime
    scaled_jobs: list[KubernetesResourceSummary] = Field(default_factory=list)
    jobs: list[KubernetesResourceSummary] = Field(default_factory=list)
    pods: list[KubernetesResourceSummary] = Field(default_factory=list)
    queue_available: bool = False
    workflow_runs: list[WorkflowLeaseSummary] = Field(default_factory=list)
    queue_error: str | None = None
    error: str | None = None


__all__ = [
    "KubernetesResourceSummary",
    "KubernetesWorkloadSnapshot",
    "WorkflowLeaseSummary",
]
