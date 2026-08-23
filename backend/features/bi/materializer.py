from datetime import UTC, datetime
from typing import Protocol

from .materialization_models import BiProfilingResult
from .models import BiMaterializationRequest


class BiDocumentProfilerPort(Protocol):
    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
