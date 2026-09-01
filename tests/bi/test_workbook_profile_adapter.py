from __future__ import annotations

from datetime import date, datetime, timezone

from backend.domains.bi.application.profile_persistence import PersistedBiDocumentProfiler
from backend.domains.bi.domain.materialization_models import BiDocumentProfile
from backend.domains.bi.domain.models import (
    AmountScale,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    CompanyId,
    IndexId,
    PeriodId,
    PeriodKind,
)
from backend.domains.bi.infrastructure.integrations.workbook_profiles import (
    WorkbookBiProfileRepository,
)
from backend.domains.data_sources.domain.workbook_profiles import (
    WorkbookAmountScale,
    WorkbookPeriodKind,
    WorkbookPeriodProfile,
    WorkbookProfile,
)

SOURCE = BiMaterializationSource(
    file_name="company.xlsx",
    workbook_hash="a" * 64,
    index_id=IndexId("idx-1"),
)
REQUEST = BiMaterializationRequest(
    company_id=CompanyId("company-1"),
    display_name="Company",
    source=SOURCE,
)


def _common(*, complete: bool) -> WorkbookProfile:
    return WorkbookProfile(
        profile_version="1",
        file_name=SOURCE.file_name,
        workbook_hash=SOURCE.workbook_hash,
        index_id=str(SOURCE.index_id),
        status="ready" if complete else "partial",
        currency="USD" if complete else None,
        amount_scale=WorkbookAmountScale.MILLIONS if complete else None,
        periods=(
            WorkbookPeriodProfile(
                period_id="fy-2025-12-31",
                kind=WorkbookPeriodKind.FY,
                label="FY2025",
                source_label="2025-12-31",
                end_date=date(2025, 12, 31),
                ordinal=2025,
            ),
        ),
        diagnostics=() if complete else ("currency_missing", "amount_scale_missing"),
    )


class MemoryProfiles:
    def __init__(self, profile: WorkbookProfile) -> None:
        self.profile = profile
        self.saved: WorkbookProfile | None = None

    def get(self, **_values: object) -> WorkbookProfile:
        return self.profile

    def save(
        self,
        profile: WorkbookProfile,
        *,
        saved_at: datetime | None = None,
    ) -> WorkbookProfile:
        self.saved = profile
        self.profile = profile
        return profile


class MemoryResolver:
    def __init__(self, profile: WorkbookProfile) -> None:
        self.profile = profile
        self.forces: list[bool] = []

    def resolve(
        self,
        *,
        file_name: str,
        workbook_hash: str,
        index_id: str,
        force: bool = False,
    ) -> WorkbookProfile:
        assert file_name == SOURCE.file_name
        assert workbook_hash == SOURCE.workbook_hash
        assert index_id == str(SOURCE.index_id)
        self.forces.append(force)
        return self.profile


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 31, tzinfo=timezone.utc)


class CountingProfiler:
    def __init__(self) -> None:
        self.calls = 0

    def profile(self, request: BiMaterializationRequest) -> BiDocumentProfile:
        self.calls += 1
        return BiDocumentProfile(
            periods=(
                BiPeriod(
                    period_id=PeriodId("fy-2025-12-31"),
                    kind=PeriodKind.FY,
                    label="FY2025",
                    source_label="2025-12-31",
                    end_date=date(2025, 12, 31),
                    ordinal=2025,
                ),
            ),
            currency="USD",
            scale=AmountScale.MILLIONS,
        )


def test_materialization_forces_original_workbook_profile_rebuild() -> None:
    stored = _common(complete=True).model_copy(update={"currency": "EUR"})
    rebuilt = _common(complete=True)
    profiles = MemoryProfiles(stored)
    resolver = MemoryResolver(rebuilt)
    adapter = WorkbookBiProfileRepository(
        profiles=profiles,
        profile_version="1",
        resolver=resolver,
    )
    fallback = CountingProfiler()

    result = PersistedBiDocumentProfiler(fallback, adapter, FixedClock()).profile(REQUEST)

    assert isinstance(result, BiDocumentProfile)
    assert result.currency == "USD"
    assert result.scale is AmountScale.MILLIONS
    assert fallback.calls == 0
    assert resolver.forces == [True]
    assert profiles.saved is None


def test_fallback_replaces_stored_profile_instead_of_merging_it() -> None:
    stale = _common(complete=True).model_copy(update={"currency": "EUR"})
    profiles = MemoryProfiles(stale)
    adapter = WorkbookBiProfileRepository(profiles=profiles, profile_version="1")
    fallback = CountingProfiler()

    result = PersistedBiDocumentProfiler(fallback, adapter, FixedClock()).profile(REQUEST)

    assert isinstance(result, BiDocumentProfile)
    assert fallback.calls == 1
    assert profiles.saved is not None
    assert profiles.saved.status == "ready"
    assert profiles.saved.currency == "USD"
    assert profiles.saved.amount_scale is WorkbookAmountScale.MILLIONS


def test_incomplete_rebuild_keeps_fresh_periods_and_uses_fallback_units() -> None:
    stale = _common(complete=True)
    fresh_period = WorkbookPeriodProfile(
        period_id="fy-2024-12-31",
        kind=WorkbookPeriodKind.FY,
        label="FY2024",
        source_label="2024-12-31",
        end_date=date(2024, 12, 31),
        ordinal=2024,
    )
    rebuilt = _common(complete=False).model_copy(
        update={"periods": (fresh_period,)}
    )
    profiles = MemoryProfiles(stale)
    resolver = MemoryResolver(rebuilt)
    adapter = WorkbookBiProfileRepository(
        profiles=profiles,
        profile_version="1",
        resolver=resolver,
    )
    fallback = CountingProfiler()

    result = PersistedBiDocumentProfiler(fallback, adapter, FixedClock()).profile(REQUEST)

    assert isinstance(result, BiDocumentProfile)
    assert tuple(str(item.period_id) for item in result.periods) == ("fy-2024-12-31",)
    assert result.currency == "USD"
    assert result.scale is AmountScale.MILLIONS
    assert resolver.forces == [True]
    assert fallback.calls == 1
    assert profiles.saved is not None
    assert tuple(item.period_id for item in profiles.saved.periods) == ("fy-2024-12-31",)
