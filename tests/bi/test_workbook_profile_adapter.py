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


def test_ready_common_profile_skips_llm_fallback() -> None:
    profiles = MemoryProfiles(_common(complete=True))
    adapter = WorkbookBiProfileRepository(profiles=profiles, profile_version="1")
    fallback = CountingProfiler()

    result = PersistedBiDocumentProfiler(fallback, adapter, FixedClock()).profile(REQUEST)

    assert isinstance(result, BiDocumentProfile)
    assert result.currency == "USD"
    assert result.scale is AmountScale.MILLIONS
    assert fallback.calls == 0
    assert profiles.saved is None


def test_partial_common_profile_uses_and_merges_llm_fallback() -> None:
    profiles = MemoryProfiles(_common(complete=False))
    adapter = WorkbookBiProfileRepository(profiles=profiles, profile_version="1")
    fallback = CountingProfiler()

    result = PersistedBiDocumentProfiler(fallback, adapter, FixedClock()).profile(REQUEST)

    assert isinstance(result, BiDocumentProfile)
    assert fallback.calls == 1
    assert profiles.saved is not None
    assert profiles.saved.status == "ready"
    assert profiles.saved.currency == "USD"
    assert profiles.saved.amount_scale is WorkbookAmountScale.MILLIONS
