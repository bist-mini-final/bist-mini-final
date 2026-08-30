from datetime import UTC, datetime
from typing import Protocol

from backend.domains.bi.domain.materialization_models import BiProfilingResult
from backend.domains.bi.domain.models import BiMaterializationRequest


class BiDocumentProfilerPort(Protocol):
    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
