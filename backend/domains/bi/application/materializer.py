"""BI materialization application contracts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from backend.domains.bi.domain.materialization_models import (
    BiMaterializationOutcome,
    BiProfilingResult,
)
from backend.domains.bi.domain.models import (
    BiMaterializationJob,
    BiMaterializationRequest,
    JobId,
)


class BiDocumentProfilerPort(Protocol):
    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class ClaimedBiMaterialization:
    request: BiMaterializationRequest
    job: BiMaterializationJob
    worker_id: str


class BiMaterializationRunnerPort(Protocol):
    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
