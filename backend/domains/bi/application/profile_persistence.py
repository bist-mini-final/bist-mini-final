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
    def rebuild(
        self,
        request: BiMaterializationRequest,
    ) -> BiDocumentProfile | None: ...

    def get(self, request: BiMaterializationRequest) -> BiDocumentProfile | None: ...

    def save(
        self,
        request: BiMaterializationRequest,
        profile: BiDocumentProfile,
        saved_at: datetime,
    ) -> BiDocumentProfile: ...


class PersistedBiDocumentProfiler:
    """Build a fresh source profile for every BI snapshot materialization.

    ``workbook_profiles`` is a shared derivative used by read paths, not an
    input cache for a new BI snapshot.  A materialization therefore asks the
    repository to rebuild the profile from the original workbook first.  The
    retrieval/LLM delegate is only a fresh fallback when deterministic source
    profiling cannot produce a usable period contract.
    """

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
        rebuilt = self._repository.rebuild(request)
        if rebuilt is not None and self._is_complete(rebuilt):
            return rebuilt
        profiled = self._delegate.profile(request)
        if not isinstance(profiled, BiDocumentProfile):
            return rebuilt if rebuilt is not None else profiled
        fresh = self._combine(rebuilt, profiled)
        return self._repository.save(request, fresh, self._clock.now())

    @staticmethod
    def _is_complete(profile: BiDocumentProfile) -> bool:
        return bool(profile.periods and profile.currency and profile.scale)

    @staticmethod
    def _combine(
        rebuilt: BiDocumentProfile | None,
        fallback: BiDocumentProfile,
    ) -> BiDocumentProfile:
        if rebuilt is None:
            return fallback
        evidence_by_id = {
            item.cell_id: item
            for item in (*rebuilt.evidence, *fallback.evidence)
        }
        return BiDocumentProfile(
            periods=rebuilt.periods,
            currency=rebuilt.currency or fallback.currency,
            scale=rebuilt.scale or fallback.scale,
            relevant_sheets=tuple(
                dict.fromkeys((*rebuilt.relevant_sheets, *fallback.relevant_sheets))
            ),
            evidence=tuple(evidence_by_id.values()),
        )


__all__ = [
    "BiDocumentProfileRepositoryPort",
    "PersistedBiDocumentProfiler",
]
