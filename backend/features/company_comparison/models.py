from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.features.bi.models import (
    IDENTIFIER_PATTERN,
    AmountScale,
    BiContractModel,
    CompanyId,
    MetricId,
)


class CompanyComparisonRequest(BiContractModel):
    company_ids: tuple[CompanyId, ...] = Field(min_length=2, max_length=3)
    start_year: int = Field(ge=1900, le=2200)
    end_year: int = Field(ge=1900, le=2200)
    question: str | None = Field(default=None, min_length=5, max_length=500)

    @field_validator("company_ids")
    @classmethod
    def require_unique_companies(
        cls,
        value: tuple[CompanyId, ...],
    ) -> tuple[CompanyId, ...]:
        if len(set(value)) != len(value):
            raise ValueError("company_ids must be unique")
        return value

    @model_validator(mode="after")
    def require_year_range(self) -> "CompanyComparisonRequest":
        if self.start_year >= self.end_year:
            raise ValueError("start_year must be earlier than end_year")
        return self


class ComparisonPoint(BiContractModel):
    year: int
    revenue: float
    operating_income: float


class ComparisonCompanyResult(BiContractModel):
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    scale: AmountScale
    points: tuple[ComparisonPoint, ...] = Field(min_length=2)
    revenue_cagr: float
    operating_margin: float
    liabilities_to_assets: float
    net_debt: float
    stability_basis_year: int = Field(ge=1900, le=2200)


class ComparisonEvidence(BiContractModel):
    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$")
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    file_name: str = Field(min_length=1, max_length=255)
    sheet_name: str = Field(min_length=1, max_length=128)
    cell_coord: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    source_text: str = Field(min_length=1, max_length=2_000)
    origin: Literal["snapshot", "rag"]


class ComparisonBriefSection(BiContractModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=40, max_length=1_200)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=12)


class CompanyComparisonBrief(BiContractModel):
    compared_company_ids: tuple[CompanyId, ...] = Field(min_length=2, max_length=3)
    growth: ComparisonBriefSection
    profitability: ComparisonBriefSection
    risk: ComparisonBriefSection
    caveats: tuple[str, ...] = Field(default=(), max_length=8)


class BriefStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"


class EvaluationType(StrEnum):
    GROWTH = "growth"
    PROFITABILITY = "profitability"
    STABILITY = "stability"
    COMPREHENSIVE = "comprehensive"


class ComparisonChartId(StrEnum):
    REVENUE_TREND = "revenue_trend"
    OPERATING_INCOME_TREND = "operating_income_trend"
    GROWTH_PROFITABILITY = "growth_profitability"
    STABILITY = "stability"


class ComparisonQuestionPlan(BiContractModel):
    evaluation_type: EvaluationType
    rationale: str = Field(min_length=10, max_length=400)


class ComparisonQueryAnalysis(BiContractModel):
    question: str = Field(min_length=5, max_length=500)
    evaluation_type: EvaluationType
    evaluation_label: str = Field(min_length=1, max_length=40)
    rationale: str = Field(min_length=10, max_length=400)
    required_metrics: tuple[MetricId, ...] = Field(min_length=1)
    chart_ids: tuple[ComparisonChartId, ...] = Field(min_length=1)


class ComparisonMeta(BiContractModel):
    generated_at: datetime
    snapshot_ids: tuple[str, ...]
    evidence_count: int = Field(ge=0)
    prompt_version: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=80)
    latency_ms: int = Field(ge=0)
    cache_hit: bool = False


class CompanyComparisonResponse(BiContractModel):
    schema_version: Literal[2] = 2
    analysis_id: str = Field(pattern=IDENTIFIER_PATTERN)
    analysis_mode: Literal["rag"] = "rag"
    brief_status: BriefStatus
    start_year: int
    end_year: int
    query_analysis: ComparisonQueryAnalysis | None = None
    companies: tuple[ComparisonCompanyResult, ...] = Field(min_length=2, max_length=3)
    brief: CompanyComparisonBrief | None
    evidence: tuple[ComparisonEvidence, ...]
    warnings: tuple[str, ...] = ()
    meta: ComparisonMeta


class FinancialTier(StrEnum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class FinancialCandle(BiContractModel):
    year: int = Field(ge=1900, le=2200)
    period_type: Literal["historical", "forecast"]
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    revenue: float = Field(ge=0)
    operating_income: float
    operating_margin: float
    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$")

    @model_validator(mode="after")
    def require_valid_range(self) -> "FinancialCandle":
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("candle low/high must contain open and close")
        return self


class LeagueCompany(BiContractModel):
    company_id: str = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    scale: AmountScale
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
    candles: tuple[FinancialCandle, ...] = Field(min_length=8, max_length=8)


class LeagueDistributionBucket(BiContractModel):
    label: str = Field(min_length=1, max_length=30)
    count: int = Field(ge=0)


class LeagueSpotlight(BiContractModel):
    leader_company_id: str = Field(pattern=IDENTIFIER_PATTERN)
    riser_company_id: str = Field(pattern=IDENTIFIER_PATTERN)
    average_cagr: float
    average_margin: float
    cagr_distribution: tuple[LeagueDistributionBucket, ...]
    margin_distribution: tuple[LeagueDistributionBucket, ...]


class FinancialLeagueResponse(BiContractModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    historical_end_year: Literal[2025] = 2025
    companies: tuple[LeagueCompany, ...] = Field(min_length=15, max_length=30)
    spotlight: LeagueSpotlight
    evidence: tuple[ComparisonEvidence, ...]


__all__ = [
    "BriefStatus",
    "CompanyComparisonBrief",
    "CompanyComparisonRequest",
    "CompanyComparisonResponse",
    "ComparisonBriefSection",
    "ComparisonChartId",
    "ComparisonCompanyResult",
    "ComparisonEvidence",
    "ComparisonMeta",
    "ComparisonPoint",
    "ComparisonQueryAnalysis",
    "ComparisonQuestionPlan",
    "EvaluationType",
    "FinancialCandle",
    "FinancialLeagueResponse",
    "FinancialTier",
    "LeagueCompany",
    "LeagueDistributionBucket",
    "LeagueSpotlight",
]
