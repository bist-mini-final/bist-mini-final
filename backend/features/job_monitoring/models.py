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


class KubernetesWorkloadSnapshot(BaseModel):
    available: bool
    source: Literal["in_cluster", "kubectl", "unavailable"]
    namespace: str
    context: str | None = None
    collected_at: datetime
    scaled_jobs: list[KubernetesResourceSummary] = Field(default_factory=list)
    jobs: list[KubernetesResourceSummary] = Field(default_factory=list)
    pods: list[KubernetesResourceSummary] = Field(default_factory=list)
    error: str | None = None


__all__ = ["KubernetesResourceSummary", "KubernetesWorkloadSnapshot"]
