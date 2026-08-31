"""Persistence decorator contract for BI document profiling."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from backend.domains.bi.domain.materialization_models import (
    BiDocumentProfile,
    BiProfilingResult,
)
from backend.domains.bi.domain.models import BiMaterializationRequest


class BiProfileClockPort(Protocol):
    def now(self) -> datetime: ...


class BiDocumentProfilerPort(Protocol):
    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult: ...


class BiDocumentProfileRepositoryPort(Protocol):
    def get(self, request: BiMaterializationRequest) -> BiDocumentProfile | None: ...

    def save(
        self,
        request: BiMaterializationRequest,
        profile: BiDocumentProfile,
        saved_at: datetime,
    ) -> BiDocumentProfile: ...


class PersistedBiDocumentProfiler:
    def __init__(
        self,
        delegate: BiDocumentProfilerPort,
        repository: BiDocumentProfileRepositoryPort,
        clock: BiProfileClockPort,
    ) -> None:
        self._delegate = delegate
        self._repository = repository
        self._clock = clock

    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult:
        stored = self._repository.get(request)
        if stored is not None:
            return stored
        profiled = self._delegate.profile(request)
        if not isinstance(profiled, BiDocumentProfile):
            return profiled
        return self._repository.save(request, profiled, self._clock.now())


__all__ = [
    "BiDocumentProfileRepositoryPort",
    "PersistedBiDocumentProfiler",
]
