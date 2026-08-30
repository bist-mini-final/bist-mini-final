"""Typed contracts for the durable company-comparison snapshot."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from backend.domains.bi.domain.models import (
    IDENTIFIER_PATTERN,
    AmountScale,
    BiContractModel,
    CompanyId,
    MetricId,
    SnapshotStatus,
)


class FinancialTier(StrEnum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class ComparisonSnapshotMeta(BiContractModel):
    snapshot_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: SnapshotStatus
    generated_at: datetime
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_snapshot_ids: tuple[str, ...] = Field(min_length=2, max_length=30)
    scoring_version: str = Field(min_length=1, max_length=40)
    forecast_version: str = Field(min_length=1, max_length=40)


class ComparisonPeriod(BiContractModel):
    year: int = Field(ge=1900, le=2200)
    period_type: Literal["historical", "forecast"]
    revenue: float = Field(ge=0)
    operating_income: float
    operating_margin: float
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    assumption_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def require_forecast_assumption(self) -> "ComparisonPeriod":
        if self.period_type == "forecast" and self.assumption_id is None:
            raise ValueError("forecast periods require assumption_id")
        if self.period_type == "historical" and self.assumption_id is not None:
            raise ValueError("historical periods cannot declare assumption_id")
        return self


class ComparisonCompany(BiContractModel):
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    scale: AmountScale
    source_snapshot_id: str = Field(pattern=IDENTIFIER_PATTERN)
    historical_start_year: int = Field(ge=1900, le=2200)
    historical_end_year: int = Field(ge=1900, le=2200)
    rank: int = Field(ge=1)
    previous_rank: int = Field(ge=1)
    rank_change: int
    composite_score: float = Field(ge=0, le=100)
    growth_score: float = Field(ge=0, le=100)
    profitability_score: float = Field(ge=0, le=100)
    stability_score: float = Field(ge=0, le=100)
    revenue_cagr: float
    operating_margin: float
    liabilities_to_assets: float = Field(ge=0)
    net_debt: float
    net_debt_to_revenue: float
    tier: FinancialTier
    periods: tuple[ComparisonPeriod, ...] = Field(min_length=5, max_length=8)


class ComparisonEvidence(BiContractModel):
    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$")
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    metric_id: MetricId
    year: int | None = Field(default=None, ge=1900, le=2200)
    file_name: str = Field(min_length=1, max_length=255)
    sheet_name: str = Field(min_length=1, max_length=128)
    cell_coord: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    source_text: str = Field(min_length=1, max_length=2_000)
    origin: Literal["bi_snapshot"] = "bi_snapshot"


class ComparisonExclusion(BiContractModel):
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=8)


class ComparisonAssumption(BiContractModel):
    assumption_id: str = Field(pattern=IDENTIFIER_PATTERN)
    description: str = Field(min_length=10, max_length=500)


class ComparisonDistributionBucket(BiContractModel):
    label: str = Field(min_length=1, max_length=30)
    count: int = Field(ge=0)


class ComparisonSpotlight(BiContractModel):
    leader_company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    riser_company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    average_cagr: float
    average_margin: float
    average_liabilities_to_assets: float
    cagr_distribution: tuple[ComparisonDistributionBucket, ...]
    margin_distribution: tuple[ComparisonDistributionBucket, ...]


def _validate_company_identity(snapshot: "CompanyComparisonSnapshot") -> list[str]:
    company_ids = [str(company.company_id) for company in snapshot.companies]
    if len(company_ids) != len(set(company_ids)):
        raise ValueError("company ids must be unique")
    if min(company.rank for company in snapshot.companies) != 1:
        raise ValueError("company ranks must start at one")
    source_ids = {company.source_snapshot_id for company in snapshot.companies}
    if source_ids != set(snapshot.snapshot.source_snapshot_ids):
        raise ValueError("source snapshot ids must match included companies")
    return company_ids


def _snapshot_link_ids(
    snapshot: "CompanyComparisonSnapshot",
) -> tuple[set[str], set[str]]:
    evidence_ids = [item.evidence_id for item in snapshot.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence ids must be unique")
    return set(evidence_ids), {item.assumption_id for item in snapshot.assumptions}


def _validate_period_links(
    periods: tuple[ComparisonPeriod, ...],
    evidence_ids: set[str],
    assumption_ids: set[str],
) -> None:
    for period in periods:
        if not set(period.evidence_ids) <= evidence_ids:
            raise ValueError("period evidence ids must resolve inside the snapshot")
        if period.assumption_id is not None and period.assumption_id not in assumption_ids:
            raise ValueError("forecast assumption ids must resolve inside the snapshot")


def _validate_company_periods(
    company: ComparisonCompany,
    evidence_ids: set[str],
    assumption_ids: set[str],
) -> None:
    historical = [period for period in company.periods if period.period_type == "historical"]
    forecasts = [period for period in company.periods if period.period_type == "forecast"]
    if len(historical) < 2 or len(forecasts) != 3:
        raise ValueError("each company requires at least two actuals and three forecasts")
    if [period.year for period in company.periods] != sorted(
        period.year for period in company.periods
    ):
        raise ValueError("company periods must be ordered by year")
    if (
        historical[0].year != company.historical_start_year
        or historical[-1].year != company.historical_end_year
    ):
        raise ValueError("company historical range must match its periods")
    if forecasts[0].year != company.historical_end_year + 1:
        raise ValueError("forecast periods must follow the latest historical year")
    _validate_period_links(company.periods, evidence_ids, assumption_ids)


def _validate_snapshot_ranges(snapshot: "CompanyComparisonSnapshot") -> None:
    expected_start = min(company.historical_start_year for company in snapshot.companies)
    expected_end = max(company.historical_end_year for company in snapshot.companies)
    if (
        snapshot.historical_start_year != expected_start
        or snapshot.historical_end_year != expected_end
    ):
        raise ValueError("snapshot historical range must match included companies")
    expected_forecast_end = max(
        period.year
        for company in snapshot.companies
        for period in company.periods
        if period.period_type == "forecast"
    )
    if snapshot.forecast_end_year != expected_forecast_end:
        raise ValueError("snapshot forecast range must match included companies")


def _validate_snapshot_status(snapshot: "CompanyComparisonSnapshot") -> None:
    if (snapshot.snapshot.status is SnapshotStatus.PARTIAL) != bool(snapshot.exclusions):
        raise ValueError("partial status must match the exclusion list")


def _validate_spotlight(snapshot: "CompanyComparisonSnapshot", company_ids: list[str]) -> None:
    if str(snapshot.spotlight.leader_company_id) not in company_ids:
        raise ValueError("spotlight leader must be an included company")
    if str(snapshot.spotlight.riser_company_id) not in company_ids:
        raise ValueError("spotlight riser must be an included company")
    expected_count = len(snapshot.companies)
    distributions = (
        snapshot.spotlight.cagr_distribution,
        snapshot.spotlight.margin_distribution,
    )
    if any(
        sum(bucket.count for bucket in distribution) != expected_count
        for distribution in distributions
    ):
        raise ValueError("distribution buckets must cover every included company")


class CompanyComparisonSnapshot(BiContractModel):
    schema_version: Literal[1] = 1
    snapshot: ComparisonSnapshotMeta
    historical_start_year: int = Field(ge=1900, le=2200)
    historical_end_year: int = Field(ge=1900, le=2200)
    forecast_end_year: int = Field(ge=1900, le=2200)
    companies: tuple[ComparisonCompany, ...] = Field(min_length=2, max_length=30)
    spotlight: ComparisonSpotlight
    evidence: tuple[ComparisonEvidence, ...]
    exclusions: tuple[ComparisonExclusion, ...] = ()
    assumptions: tuple[ComparisonAssumption, ...] = ()

    @model_validator(mode="after")
    def validate_snapshot_links(self) -> "CompanyComparisonSnapshot":
        company_ids = _validate_company_identity(self)
        evidence_ids, assumption_ids = _snapshot_link_ids(self)
        for company in self.companies:
            _validate_company_periods(company, evidence_ids, assumption_ids)
        _validate_snapshot_ranges(self)
        _validate_snapshot_status(self)
        _validate_spotlight(self, company_ids)
        return self


__all__ = [
    "CompanyComparisonSnapshot",
    "ComparisonAssumption",
    "ComparisonCompany",
    "ComparisonDistributionBucket",
    "ComparisonEvidence",
    "ComparisonExclusion",
    "ComparisonPeriod",
    "ComparisonSnapshotMeta",
    "ComparisonSpotlight",
    "FinancialTier",
]
