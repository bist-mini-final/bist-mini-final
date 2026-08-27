from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import pairwise
from math import pow
from statistics import fmean
from typing import Final, Protocol, TypedDict

from backend.features.bi.materialization_models import BiCompanyIndexEntry
from backend.features.bi.models import (
    AmountScale,
    AvailableObservation,
    BiDashboardSnapshot,
    BiEvidence,
    CompanyId,
    MetricId,
)

from .calculator import ComparisonDataError
from .models import (
    ComparisonEvidence,
    FinancialCandle,
    FinancialLeagueResponse,
    FinancialTier,
    LeagueCompany,
    LeagueDistributionBucket,
    LeagueSpotlight,
)

HISTORICAL_YEARS: Final = tuple(range(2021, 2026))
FORECAST_YEARS: Final = tuple(range(2026, 2029))
MIN_LEAGUE_COMPANIES: Final = 15
MAX_LEAGUE_COMPANIES: Final = 30


@dataclass(frozen=True, slots=True)
class BaseFinancials:
    company_id: CompanyId
    display_name: str
    currency: str
    scale: AmountScale
    revenues: dict[int, float]
    margins: dict[int, float]
    liabilities_to_assets: float
    net_debt: float
    file_name: str
    evidence: BiEvidence


class FinancialLeagueStorePort(Protocol):
    def list_companies(self) -> tuple[BiCompanyIndexEntry, ...]: ...

    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None: ...


class LeagueCandidate(TypedDict):
    company_id: CompanyId
    display_name: str
    currency: str
    scale: AmountScale
    composite_score: float
    growth_score: float
    profitability_score: float
    stability_score: float
    revenue_cagr: float
    operating_margin: float
    liabilities_to_assets: float
    net_debt: float
    tier: FinancialTier
    candles: tuple[FinancialCandle, ...]
    historical_score: float


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _round(value: float) -> float:
    return round(value, 2)


def _year(snapshot: BiDashboardSnapshot, period_id: str) -> int | None:
    period = next((item for item in snapshot.periods if item.period_id == period_id), None)
    if period is None or period.kind.value != "fy":
        return None
    if period.end_date is not None:
        return period.end_date.year
    digits = "".join(character for character in period.label if character.isdigit())[:4]
    return int(digits) if len(digits) == 4 else None


def _series(snapshot: BiDashboardSnapshot, metric_id: MetricId) -> dict[int, AvailableObservation]:
    metric = snapshot.metrics.get(metric_id)
    if metric is None:
        return {}
    return {
        year: item
        for item in metric.observations
        if isinstance(item, AvailableObservation)
        and (year := _year(snapshot, str(item.period_id))) is not None
    }


def _latest_value(snapshot: BiDashboardSnapshot, metric_id: MetricId) -> float | None:
    values = _series(snapshot, metric_id)
    return float(values[max(values)].normalized_value) if values else None


def _base_from_snapshot(snapshot: BiDashboardSnapshot) -> BaseFinancials | None:
    revenue_series = snapshot.metrics.get(MetricId.REVENUE)
    revenues_raw = _series(snapshot, MetricId.REVENUE)
    income_raw = _series(snapshot, MetricId.OPERATING_INCOME)
    common = sorted(set(revenues_raw) & set(income_raw))
    if not common or revenue_series is None or revenue_series.currency is None or revenue_series.scale is None:
        return None
    actual_revenues = {year: float(revenues_raw[year].normalized_value) for year in common}
    actual_margins = {
        year: float(income_raw[year].normalized_value / revenues_raw[year].normalized_value * Decimal(100))
        for year in common
        if revenues_raw[year].normalized_value > 0
    }
    if not actual_margins:
        return None
    first_year, last_year = min(common), max(common)
    span = max(1, last_year - first_year)
    growth = pow(actual_revenues[last_year] / actual_revenues[first_year], 1 / span) - 1
    revenues: dict[int, float] = {}
    anchor = actual_revenues[last_year]
    for year in HISTORICAL_YEARS:
        revenues[year] = actual_revenues.get(year, anchor / pow(1 + growth, last_year - year))
    margins = {year: actual_margins.get(year, actual_margins[last_year]) for year in HISTORICAL_YEARS}
    liabilities = _latest_value(snapshot, MetricId.TOTAL_LIABILITIES) or anchor * 0.34
    assets = _latest_value(snapshot, MetricId.TOTAL_ASSETS) or anchor * 0.82
    net_debt = _latest_value(snapshot, MetricId.NET_DEBT) or 0.0
    evidence = revenues_raw[last_year].evidence[0] if revenues_raw[last_year].evidence else BiEvidence(
        cell_id=f"{snapshot.company.company_id}-revenue-{last_year}",
        sheet_name="Financials",
        cell_coord="A1",
        source_text=f"{snapshot.company.display_name} {last_year} revenue",
    )
    return BaseFinancials(
        company_id=snapshot.company.company_id,
        display_name=snapshot.company.display_name,
        currency=revenue_series.currency,
        scale=revenue_series.scale,
        revenues=revenues,
        margins=margins,
        liabilities_to_assets=max(0.0, liabilities / assets * 100),
        net_debt=net_debt,
        file_name=snapshot.source.file_name,
        evidence=evidence,
    )


class FinancialLeagueService:
    def __init__(self, store: FinancialLeagueStorePort) -> None:
        self._store = store

    def build(self) -> FinancialLeagueResponse:
        bases = self._load_bases()
        if len(bases) < MIN_LEAGUE_COMPANIES:
            raise ComparisonDataError(
                "financial_league_insufficient_companies",
                f"재무 리그에는 파싱 완료된 기업이 최소 {MIN_LEAGUE_COMPANIES}개 필요합니다. 현재 {len(bases)}개입니다.",
            )
        evidence: list[ComparisonEvidence] = []
        candidates: list[LeagueCandidate] = []
        for evidence_index, base in enumerate(bases, 1):
            evidence_id = f"E{evidence_index}"
            evidence.append(ComparisonEvidence(
                evidence_id=evidence_id,
                company_id=base.company_id,
                file_name=base.file_name,
                sheet_name=base.evidence.sheet_name,
                cell_coord=base.evidence.cell_coord,
                source_text=base.evidence.source_text,
                origin="snapshot",
            ))
            candidates.append(self._candidate(base, evidence_id))

        previous_order = sorted(candidates, key=lambda item: item["historical_score"], reverse=True)
        previous_rank = {str(item["company_id"]): rank for rank, item in enumerate(previous_order, 1)}
        current_order = sorted(candidates, key=lambda item: item["composite_score"], reverse=True)
        companies = tuple(
            LeagueCompany(
                company_id=item["company_id"],
                display_name=item["display_name"],
                currency=item["currency"],
                scale=item["scale"],
                rank=rank,
                previous_rank=previous_rank[str(item["company_id"])],
                rank_change=previous_rank[str(item["company_id"])] - rank,
                composite_score=item["composite_score"],
                growth_score=item["growth_score"],
                profitability_score=item["profitability_score"],
                stability_score=item["stability_score"],
                revenue_cagr=item["revenue_cagr"],
                operating_margin=item["operating_margin"],
                liabilities_to_assets=item["liabilities_to_assets"],
                net_debt=item["net_debt"],
                tier=item["tier"],
                candles=item["candles"],
            )
            for rank, item in enumerate(current_order, 1)
        )
        riser = max(companies, key=lambda item: (item.rank_change, item.composite_score))
        return FinancialLeagueResponse(
            generated_at=datetime.now(timezone.utc),
            companies=companies,
            spotlight=LeagueSpotlight(
                leader_company_id=companies[0].company_id,
                riser_company_id=riser.company_id,
                average_cagr=_round(fmean(item.revenue_cagr for item in companies)),
                average_margin=_round(fmean(item.operating_margin for item in companies)),
                cagr_distribution=self._distribution([item.revenue_cagr for item in companies], (-5, 5, 10, 15, 20, 30)),
                margin_distribution=self._distribution([item.operating_margin for item in companies], (0, 5, 10, 15, 20, 30)),
            ),
            evidence=tuple(evidence),
        )

    def _load_bases(self) -> tuple[BaseFinancials, ...]:
        try:
            entries = self._store.list_companies()
            snapshots = tuple(
                snapshot
                for entry in entries
                if (snapshot := self._store.get_current(entry.company.company_id)) is not None
            )
            loaded = tuple(item for snapshot in snapshots if (item := _base_from_snapshot(snapshot)) is not None)
        except (AttributeError, KeyError, ValueError):
            return ()
        return loaded[:MAX_LEAGUE_COMPANIES]

    def _candidate(self, base: BaseFinancials, evidence_id: str) -> LeagueCandidate:
        historical_growth = pow(base.revenues[2025] / base.revenues[2021], 1 / 4) - 1
        forecast_growth = max(-0.12, historical_growth)
        revenue_by_year = dict(base.revenues)
        margin_by_year = dict(base.margins)
        for year in FORECAST_YEARS:
            revenue_by_year[year] = revenue_by_year[year - 1] * (1 + forecast_growth)
            margin_by_year[year] = margin_by_year[year - 1]
        cagr = (pow(revenue_by_year[2028] / revenue_by_year[2025], 1 / 3) - 1) * 100
        margin = margin_by_year[2028]
        debt_ratio = base.liabilities_to_assets
        net_debt = base.net_debt - (revenue_by_year[2028] - base.revenues[2025]) * 0.08
        growth_score = _clamp((cagr + 5) / 30 * 100)
        profitability_score = _clamp((margin + 5) / 30 * 100)
        net_cash_bonus = 14 if net_debt <= 0 else -min(22, net_debt / max(revenue_by_year[2028], 1) * 100)
        stability_score = _clamp(100 - debt_ratio * 1.15 + net_cash_bonus)
        growth_score = _round(growth_score)
        profitability_score = _round(profitability_score)
        stability_score = _round(stability_score)
        composite = growth_score * 0.35 + profitability_score * 0.35 + stability_score * 0.30
        historical_margin = margin_by_year[2025]
        historical_growth_score = _clamp((historical_growth * 100 + 5) / 30 * 100)
        historical_profit_score = _clamp((historical_margin + 5) / 30 * 100)
        historical_stability = _clamp(100 - base.liabilities_to_assets * 1.15 + (14 if base.net_debt <= 0 else -8))
        historical_score = historical_growth_score * 0.35 + historical_profit_score * 0.35 + historical_stability * 0.30
        tier = FinancialTier.S if composite >= 90 else FinancialTier.A if composite >= 75 else FinancialTier.B if composite >= 60 else FinancialTier.C
        candles = tuple(
            self._candle(year, revenue_by_year[year], margin_by_year[year], evidence_id)
            for year in (*HISTORICAL_YEARS, *FORECAST_YEARS)
        )
        return {
            "company_id": base.company_id,
            "display_name": base.display_name,
            "currency": base.currency,
            "scale": base.scale,
            "composite_score": _round(composite),
            "growth_score": _round(growth_score),
            "profitability_score": _round(profitability_score),
            "stability_score": _round(stability_score),
            "revenue_cagr": _round(cagr),
            "operating_margin": _round(margin),
            "liabilities_to_assets": _round(debt_ratio),
            "net_debt": _round(net_debt),
            "tier": tier,
            "candles": candles,
            "historical_score": historical_score,
        }

    @staticmethod
    def _candle(year: int, annual_revenue: float, margin: float, evidence_id: str) -> FinancialCandle:
        seasonality = (0.225, 0.242, 0.252, 0.281)
        quarterly_run_rates = [annual_revenue * value * 4 for value in seasonality]
        return FinancialCandle(
            year=year,
            period_type="historical" if year <= 2025 else "forecast",
            open=_round(quarterly_run_rates[0]),
            high=_round(max(quarterly_run_rates) * 1.035),
            low=_round(min(quarterly_run_rates) * 0.965),
            close=_round(quarterly_run_rates[-1]),
            revenue=_round(annual_revenue),
            operating_income=_round(annual_revenue * margin / 100),
            operating_margin=_round(margin),
            evidence_id=evidence_id,
        )

    @staticmethod
    def _distribution(values: list[float], edges: tuple[int, ...]) -> tuple[LeagueDistributionBucket, ...]:
        buckets: list[LeagueDistributionBucket] = []
        for low, high in pairwise(edges):
            buckets.append(LeagueDistributionBucket(label=f"{low}-{high}%", count=sum(low <= value < high for value in values)))
        buckets.append(LeagueDistributionBucket(label=f"{edges[-1]}%+", count=sum(value >= edges[-1] for value in values)))
        return tuple(buckets)


__all__ = ["FinancialLeagueService", "FinancialLeagueStorePort"]
