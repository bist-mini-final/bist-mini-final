from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.company_comparison_routes import create_company_comparison_router
from backend.contracts.snapshots import VersionedSnapshotRecord
from backend.domains.bi.domain.materialization_models import BiCompanyIndexEntry
from backend.domains.bi.domain.models import (
    AmountScale,
    AvailableObservation,
    BiCompany,
    BiDashboardSnapshot,
    BiEvidence,
    BiMaterializationSource,
    BiPeriod,
    BiRefreshState,
    BiSnapshotMeta,
    CompanyId,
    IndexId,
    MetricId,
    MetricSeries,
    MetricStatus,
    PeriodId,
    PeriodKind,
    RefreshStatus,
    SnapshotId,
    SnapshotStatus,
    ValueKind,
)
from backend.domains.company_comparison.application import CompanyComparisonService
from backend.domains.company_comparison.errors import ComparisonDataError
from backend.domains.company_comparison.models import CompanyComparisonSnapshot
from backend.domains.company_comparison.snapshot_builder import (
    CompanyComparisonSnapshotBuilder,
)


def _snapshot(
    company_id: str,
    name: str,
    *,
    growth: Decimal,
    margin: Decimal,
    net_debt: Decimal = Decimal("10"),
    include_assets: bool = True,
    financial_position_year: int = 2025,
    extra_revenue_evidence: bool = False,
    placeholder_revenue_evidence: bool = False,
) -> BiDashboardSnapshot:
    years = range(2022, 2026)
    periods = tuple(
        BiPeriod(
            period_id=PeriodId(f"fy-{year}"),
            kind=PeriodKind.FY,
            label=str(year),
            source_label=f"FY {year}",
            end_date=datetime(year, 12, 31).date(),
            ordinal=index,
        )
        for index, year in enumerate(years, 1)
    )

    def observation(metric: MetricId, year: int, value: Decimal) -> AvailableObservation:
        evidence = [
            BiEvidence(
                cell_id=f"{company_id}-{metric.value}-{year}",
                sheet_name="Financials",
                cell_coord=f"B{year - 2000}",
                source_text=(
                    f"Company: {name} | Sheet: Financials | Row Header: {metric.value} | "
                    f"Column Header: {year} | Cell Value: {value}"
                ),
            )
        ]
        if extra_revenue_evidence and metric is MetricId.REVENUE and year == 2022:
            evidence.append(
                BiEvidence(
                    cell_id=f"{company_id}-{metric.value}-{year}-note",
                    sheet_name="Financials",
                    cell_coord=f"C{year - 2000}",
                    source_text=(
                        f"Company: {name} | Sheet: Financials | Row Header: {metric.value} | "
                        f"Column Header: {year} supporting note | Cell Value: {value}"
                    ),
                )
            )
        if placeholder_revenue_evidence and metric is MetricId.REVENUE and year == 2022:
            evidence.append(
                BiEvidence(
                    cell_id=f"{company_id}-{metric.value}-{year}-placeholder",
                    sheet_name="Financials",
                    cell_coord=f"D{year - 2000}",
                    source_text=(
                        f"Company: {name} | Sheet: Financials | Row Header: {metric.value} | "
                        f"Column Header: {year} | Cell Value: ?"
                    ),
                )
            )
        return AvailableObservation(
            period_id=PeriodId(f"fy-{year}"),
            status=MetricStatus.AVAILABLE,
            raw_value=str(value),
            normalized_value=value,
            evidence=tuple(evidence),
        )

    def amount_series(metric: MetricId, values: dict[int, Decimal]) -> MetricSeries:
        return MetricSeries(
            metric_id=metric,
            label=metric.value,
            value_kind=ValueKind.AMOUNT,
            currency="USD",
            scale=AmountScale.MILLIONS,
            status=MetricStatus.AVAILABLE,
            observations=tuple(observation(metric, year, value) for year, value in values.items()),
        )

    revenues: dict[int, Decimal] = {}
    value = Decimal("100")
    for year in years:
        revenues[year] = value
        value *= Decimal("1") + growth
    incomes = {year: revenue * margin for year, revenue in revenues.items()}
    metrics = {
        MetricId.REVENUE: amount_series(MetricId.REVENUE, revenues),
        MetricId.OPERATING_INCOME: amount_series(MetricId.OPERATING_INCOME, incomes),
        MetricId.TOTAL_LIABILITIES: amount_series(
            MetricId.TOTAL_LIABILITIES,
            {financial_position_year: Decimal("40")},
        ),
        MetricId.NET_DEBT: amount_series(
            MetricId.NET_DEBT,
            {financial_position_year: net_debt},
        ),
    }
    if include_assets:
        metrics[MetricId.TOTAL_ASSETS] = amount_series(
            MetricId.TOTAL_ASSETS,
            {financial_position_year: Decimal("100")},
        )
    digest = ("a" if company_id.endswith("a") else "b") * 64
    return BiDashboardSnapshot(
        schema_version=1,
        company=BiCompany(company_id=CompanyId(company_id), display_name=name),
        source=BiMaterializationSource(
            file_name=f"{name}.xlsx",
            workbook_hash=digest,
            index_id=IndexId(f"index-{company_id}"),
        ),
        snapshot=BiSnapshotMeta(
            snapshot_id=SnapshotId(f"snapshot-{company_id}"),
            workbook_hash=digest,
            status=SnapshotStatus.READY,
            generated_at=datetime.now(timezone.utc),
            catalog_version="1",
            formula_version="1",
        ),
        refresh=BiRefreshState(status=RefreshStatus.IDLE),
        periods=periods,
        metrics=metrics,
        issues=(),
    )


def test_builder_uses_only_observed_financials_and_marks_forecasts() -> None:
    result = CompanyComparisonSnapshotBuilder().build(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot(
                "company-b",
                "Beta",
                growth=Decimal("0.04"),
                margin=Decimal("0.12"),
                net_debt=Decimal("0"),
            ),
        ),
        generated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )

    assert result.snapshot.status is SnapshotStatus.READY
    assert len(result.companies) == 2
    assert result.companies[0].display_name == "Alpha"
    assert result.companies[0].revenue_cagr == 10.0
    assert result.companies[1].net_debt == 0.0
    assert [period.year for period in result.companies[0].periods] == list(range(2022, 2029))
    assert all(
        period.assumption_id is None
        for period in result.companies[0].periods
        if period.period_type == "historical"
    )
    assert all(
        period.assumption_id == "historical-cagr-hold-v1"
        for period in result.companies[0].periods
        if period.period_type == "forecast"
    )
    assert {item.origin for item in result.evidence} == {"bi_snapshot"}


def test_builder_excludes_incomplete_company_without_synthetic_fallback() -> None:
    result = CompanyComparisonSnapshotBuilder().build(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
            _snapshot(
                "company-c",
                "Incomplete",
                growth=Decimal("0.03"),
                margin=Decimal("0.08"),
                include_assets=False,
            ),
        )
    )

    assert result.snapshot.status is SnapshotStatus.PARTIAL
    assert {company.display_name for company in result.companies} == {"Alpha", "Beta"}
    assert result.exclusions[0].display_name == "Incomplete"
    assert "총자산" in " ".join(result.exclusions[0].reasons)


def test_builder_aligns_financial_position_metrics_to_the_latest_comparison_year() -> None:
    result = CompanyComparisonSnapshotBuilder().build(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
            _snapshot(
                "company-c",
                "Stale Position",
                growth=Decimal("0.03"),
                margin=Decimal("0.08"),
                financial_position_year=2024,
            ),
        )
    )

    assert result.snapshot.status is SnapshotStatus.PARTIAL
    assert result.exclusions[0].display_name == "Stale Position"
    assert "비교 기준 회계연도" in " ".join(result.exclusions[0].reasons)


def test_builder_preserves_all_source_cells_for_an_observed_value() -> None:
    result = CompanyComparisonSnapshotBuilder().build(
        (
            _snapshot(
                "company-a",
                "Alpha",
                growth=Decimal("0.10"),
                margin=Decimal("0.20"),
                extra_revenue_evidence=True,
            ),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
        )
    )

    alpha = next(company for company in result.companies if company.display_name == "Alpha")
    first_period = next(period for period in alpha.periods if period.year == 2022)
    assert len(first_period.evidence_ids) == 3
    assert any(item.cell_coord == "C22" for item in result.evidence)


def test_builder_drops_placeholder_source_cells_from_comparison_evidence() -> None:
    result = CompanyComparisonSnapshotBuilder().build(
        (
            _snapshot(
                "company-a",
                "Alpha",
                growth=Decimal("0.10"),
                margin=Decimal("0.20"),
                placeholder_revenue_evidence=True,
            ),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
        )
    )

    assert all("Cell Value: ?" not in item.source_text for item in result.evidence)
    assert not any(item.cell_coord == "D22" for item in result.evidence)


def test_snapshot_contract_rejects_unresolved_period_evidence() -> None:
    snapshot = CompanyComparisonSnapshotBuilder().build(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
        )
    )
    payload = snapshot.model_dump(mode="json")
    payload["companies"][0]["periods"][0]["evidence_ids"] = ["E99999"]

    with pytest.raises(ValueError, match="period evidence ids must resolve"):
        CompanyComparisonSnapshot.model_validate(payload)


def test_builder_rejects_fewer_than_two_complete_companies() -> None:
    with pytest.raises(ComparisonDataError, match="최소 2개"):
        CompanyComparisonSnapshotBuilder().build(
            (_snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),)
        )


class FakeSource:
    def __init__(self, snapshots: tuple[BiDashboardSnapshot, ...]) -> None:
        self.items = {snapshot.company.company_id: snapshot for snapshot in snapshots}

    async def list_companies_async(self):
        return tuple(
            BiCompanyIndexEntry(
                company=snapshot.company,
                source=snapshot.source,
                current_snapshot_id=snapshot.snapshot.snapshot_id,
            )
            for snapshot in self.items.values()
        )

    async def get_current_many_async(self, company_ids):
        return {company_id: self.items[company_id] for company_id in company_ids}


class MemorySnapshotRepository:
    def __init__(self) -> None:
        self.record: VersionedSnapshotRecord | None = None
        self.publish_count = 0

    async def get_current(self, *, domain: str, scope_key: str):
        if self.record is None:
            return None
        if self.record.domain != domain or self.record.scope_key != scope_key:
            return None
        return self.record

    async def publish(self, record: VersionedSnapshotRecord) -> None:
        self.record = record
        self.publish_count += 1


@pytest.mark.anyio
async def test_service_publishes_once_for_an_unchanged_source_fingerprint() -> None:
    source = FakeSource(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
        )
    )
    repository = MemorySnapshotRepository()
    service = CompanyComparisonService(source, repository)

    first = await service.refresh()
    second = await service.refresh()

    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    assert repository.publish_count == 1
    assert await service.current() == first


@pytest.mark.anyio
async def test_current_or_refresh_automatically_adds_a_new_bi_snapshot() -> None:
    source = FakeSource(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
        )
    )
    repository = MemorySnapshotRepository()
    service = CompanyComparisonService(source, repository)
    first = await service.current_or_refresh()
    assert first is not None

    added = _snapshot(
        "company-c",
        "Gamma",
        growth=Decimal("0.07"),
        margin=Decimal("0.15"),
    )
    source.items[added.company.company_id] = added

    refreshed = await service.current_or_refresh()

    assert refreshed is not None
    assert {company.display_name for company in refreshed.companies} == {
        "Alpha",
        "Beta",
        "Gamma",
    }
    assert repository.publish_count == 2


@pytest.mark.anyio
async def test_current_or_refresh_keeps_last_snapshot_during_source_gap() -> None:
    source = FakeSource(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
        )
    )
    repository = MemorySnapshotRepository()
    service = CompanyComparisonService(source, repository)
    current = await service.refresh()
    source.items.clear()

    assert await service.current_or_refresh() == current
    assert repository.publish_count == 1


class FakeApiService:
    def __init__(self, snapshot=None) -> None:
        self.snapshot = snapshot

    async def current(self):
        return self.snapshot

    async def current_or_refresh(self):
        return self.snapshot

    async def refresh(self):
        if self.snapshot is None:
            raise ComparisonDataError("insufficient", "비교 가능한 기업이 부족합니다.")
        return self.snapshot


def test_snapshot_api_exposes_only_current_and_refresh_contracts() -> None:
    snapshot = CompanyComparisonSnapshotBuilder().build(
        (
            _snapshot("company-a", "Alpha", growth=Decimal("0.10"), margin=Decimal("0.20")),
            _snapshot("company-b", "Beta", growth=Decimal("0.04"), margin=Decimal("0.12")),
        )
    )
    app = FastAPI()
    app.include_router(
        create_company_comparison_router(FakeApiService(snapshot))  # type: ignore[arg-type]
    )
    client = TestClient(app)

    assert client.get("/company-comparisons/snapshot").status_code == 200
    assert client.post("/company-comparisons/snapshot/refresh").status_code == 200
    assert client.get("/company-comparisons/league").status_code == 404
    assert client.post("/company-comparisons/analyze").status_code == 404


def test_snapshot_api_reports_missing_and_insufficient_materializations() -> None:
    app = FastAPI()
    app.include_router(
        create_company_comparison_router(FakeApiService())  # type: ignore[arg-type]
    )
    client = TestClient(app)

    missing = client.get("/company-comparisons/snapshot")
    rejected = client.post("/company-comparisons/snapshot/refresh")

    assert missing.status_code == 404
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "INSUFFICIENT"
