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
# Absolute 100-point benchmarks calibrated from the three parsed anchor profiles.
# They are not observed-company maxima: a virtual company can outperform an anchor.
GROWTH_SCORE_FLOOR: Final = -10.0
GROWTH_SCORE_CEILING: Final = 12.0
MARGIN_SCORE_FLOOR: Final = -5.0
MARGIN_SCORE_CEILING: Final = 15.0
COMPOSITE_TIER_THRESHOLDS: Final = {
    FinancialTier.S: 90.0,
    FinancialTier.A: 75.0,
    FinancialTier.B: 50.0,
    FinancialTier.C: 0.0,
}


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
    net_debt_to_revenue: float
    tier: FinancialTier
    candles: tuple[FinancialCandle, ...]
    historical_score: float


@dataclass(frozen=True, slots=True)
class TemporaryCompanySpec:
    company_id: str
    display_name: str
    revenue_2021: float
    annual_growth_rates: tuple[float, float, float, float]
    operating_margins: tuple[float, float, float, float, float]
    liabilities_to_assets: float
    net_debt: float
    lineage: str


TEMPORARY_COMPANY_SPECS: Final = (
    # Bistelligence growth lineage: growth-oriented, with distinct margin and leverage paths.
    TemporaryCompanySpec("temp-amesoft", "Amesoft", 9_000, (.10, .111, .114, .118), (10.2, 11.0, 12.0, 13.2, 14.6), 36.0, -600, "Bistelligence growth"),
    TemporaryCompanySpec("temp-nexora-labs", "Nexora Labs", 6_800, (.147, .154, .156, .154), (3.5, 5.0, 7.0, 9.5, 12.5), 34.0, -250, "Bistelligence growth"),
    TemporaryCompanySpec("temp-veltrix-systems", "Veltrix Systems", 12_800, (.063, .088, .088, .093), (18.0, 18.4, 18.9, 19.4, 20.0), 31.0, -900, "Bistelligence growth"),
    TemporaryCompanySpec("temp-lumena-ai", "Lumena AI", 4_200, (.19, .22, .18, .125), (2.5, 4.0, 5.5, 7.0, 8.0), 58.0, 800, "Bistelligence growth"),
    TemporaryCompanySpec("temp-corevia-tech", "Corevia Tech", 15_300, (.059, .056, .07, .077), (13.2, 13.4, 13.8, 14.1, 14.6), 48.0, -200, "Bistelligence growth"),
    TemporaryCompanySpec("temp-altiven", "Altiven", 7_900, (.139, .117, .114, .098), (8.8, 9.8, 10.9, 12.2, 13.4), 40.0, 615, "Bistelligence growth"),
    # Coldplay stable lineage: steadier revenue profiles with different capital structures.
    TemporaryCompanySpec("temp-serenex-systems", "Serenex Systems", 11_400, (.053, .05, .048, .045), (21.5, 21.7, 22.0, 22.2, 22.5), 26.0, -1_200, "Coldplay stable"),
    TemporaryCompanySpec("temp-bluepeak-digital", "Bluepeak Digital", 5_800, (.103, .109, .127, .125), (4.5, 5.8, 7.0, 8.5, 10.0), 55.0, 900, "Coldplay stable"),
    TemporaryCompanySpec("temp-meridian-logic", "Meridian Logic", 13_650, (.048, .056, .06, .063), (10.0, 10.5, 11.0, 11.5, 12.0), 52.0, 900, "Coldplay stable"),
    TemporaryCompanySpec("temp-orbixa-networks", "Orbixa Networks", 8_840, (.046, .049, .057, .059), (16.5, 16.9, 17.4, 17.9, 18.5), 42.0, -600, "Coldplay stable"),
    TemporaryCompanySpec("temp-primeforge", "Primeforge", 17_200, (.035, .017, -.011, .028), (8.8, 9.0, 8.7, 8.9, 9.4), 55.0, 920, "Coldplay stable"),
    TemporaryCompanySpec("temp-solvanta", "Solvanta", 6_940, (.095, .118, .118, .095), (7.0, 8.0, 9.0, 10.0, 11.0), 54.0, 1_500, "Coldplay stable"),
    # DH Innovation decline lineage: pressure or recovery patterns without copying the anchor.
    TemporaryCompanySpec("temp-redwood-dynamics", "Redwood Dynamics", 14_100, (-.035, -.02, -.04, -.03), (8.0, 7.0, 6.0, 4.5, 3.0), 63.0, 2_200, "DH Innovation decline"),
    TemporaryCompanySpec("temp-ironvale-tech", "Ironvale Tech", 10_250, (.024, -.038, -.03, -.02), (6.2, 5.5, 4.2, 3.5, 3.0), 66.0, 1_440, "DH Innovation decline"),
    TemporaryCompanySpec("temp-northstar-materials", "Northstar Materials", 19_500, (-.026, -.032, -.033, .017), (11.5, 10.0, 8.5, 7.0, 7.8), 61.0, 3_260, "DH Innovation decline"),
)
TEMPORARY_COMPANY_COUNT: Final = len(TEMPORARY_COMPANY_SPECS)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _round(value: float) -> float:
    return round(value, 2)


def _benchmark_score(value: float, floor: float, ceiling: float) -> float:
    return _clamp((value - floor) / (ceiling - floor) * 100.0)


def growth_score(growth_percent: float) -> float:
    return _round(
        _benchmark_score(growth_percent, GROWTH_SCORE_FLOOR, GROWTH_SCORE_CEILING)
    )


def profitability_score(margin_percent: float) -> float:
    return _round(
        _benchmark_score(margin_percent, MARGIN_SCORE_FLOOR, MARGIN_SCORE_CEILING)
    )


def financial_stability_score(
    liabilities_to_assets: float, net_debt: float, annual_revenue: float
) -> float:
    """Score balance-sheet resilience using only metrics available in every snapshot.

    The leverage component reaches 100 at 30% liabilities/assets and 0 at 70%.
    The funding component reaches 100 for net-cash companies and declines to 0
    when net debt reaches 25% of annual revenue. Leverage receives the larger
    weight because it captures the whole liability structure rather than debt alone.
    """
    leverage_score = _clamp((70.0 - liabilities_to_assets) / 40.0 * 100.0)
    net_debt_ratio = net_debt / max(annual_revenue, 1.0) * 100.0
    funding_score = 100.0 if net_debt_ratio <= 0 else _clamp(100.0 - net_debt_ratio * 4.0)
    return _round(leverage_score * 0.70 + funding_score * 0.30)


def composite_tier(score: float) -> FinancialTier:
    if score >= COMPOSITE_TIER_THRESHOLDS[FinancialTier.S]:
        return FinancialTier.S
    if score >= COMPOSITE_TIER_THRESHOLDS[FinancialTier.A]:
        return FinancialTier.A
    if score >= COMPOSITE_TIER_THRESHOLDS[FinancialTier.B]:
        return FinancialTier.B
    return FinancialTier.C


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
    if (
        not common
        or revenue_series is None
        or revenue_series.currency is None
        or revenue_series.scale is None
    ):
        return None
    actual_revenues = {year: float(revenues_raw[year].normalized_value) for year in common}
    actual_margins = {
        year: float(
            income_raw[year].normalized_value / revenues_raw[year].normalized_value * Decimal(100)
        )
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
    margins = {
        year: actual_margins.get(year, actual_margins[last_year]) for year in HISTORICAL_YEARS
    }
    liabilities = _latest_value(snapshot, MetricId.TOTAL_LIABILITIES) or anchor * 0.34
    assets = _latest_value(snapshot, MetricId.TOTAL_ASSETS) or anchor * 0.82
    net_debt = _latest_value(snapshot, MetricId.NET_DEBT) or 0.0
    evidence = (
        revenues_raw[last_year].evidence[0]
        if revenues_raw[last_year].evidence
        else BiEvidence(
            cell_id=f"{snapshot.company.company_id}-revenue-{last_year}",
            sheet_name="Financials",
            cell_coord="A1",
            source_text=f"{snapshot.company.display_name} {last_year} revenue",
        )
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


def _temporary_bases() -> tuple[BaseFinancials, ...]:
    bases: list[BaseFinancials] = []
    for spec in TEMPORARY_COMPANY_SPECS:
        annual_revenues = [spec.revenue_2021]
        for growth_rate in spec.annual_growth_rates:
            annual_revenues.append(annual_revenues[-1] * (1 + growth_rate))
        revenues = dict(zip(HISTORICAL_YEARS, annual_revenues, strict=True))
        margins = dict(zip(HISTORICAL_YEARS, spec.operating_margins, strict=True))
        bases.append(
            BaseFinancials(
                company_id=CompanyId(spec.company_id),
                display_name=spec.display_name,
                currency="USD",
                scale=AmountScale.MILLIONS,
                revenues=revenues,
                margins=margins,
                liabilities_to_assets=spec.liabilities_to_assets,
                net_debt=spec.net_debt,
                file_name="company-comparison-temporary-data",
                evidence=BiEvidence(
                    cell_id=f"{spec.company_id}-temporary-revenue-2025",
                    sheet_name="Temporary_Scenario",
                    cell_coord="A1",
                    source_text=(
                        f"{spec.display_name} AI 기업 비교 화면용 임시 재무 시나리오 데이터 "
                        f"({spec.lineage} 계열 기반)"
                    ),
                ),
            )
        )
    return tuple(bases)


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
            evidence.append(
                ComparisonEvidence(
                    evidence_id=evidence_id,
                    company_id=base.company_id,
                    file_name=base.file_name,
                    sheet_name=base.evidence.sheet_name,
                    cell_coord=base.evidence.cell_coord,
                    source_text=base.evidence.source_text,
                    origin="snapshot",
                )
            )
            candidates.append(self._candidate(base, evidence_id))

        previous_order = sorted(candidates, key=lambda item: item["historical_score"], reverse=True)
        previous_rank = {
            str(item["company_id"]): rank for rank, item in enumerate(previous_order, 1)
        }
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
                net_debt_to_revenue=item["net_debt_to_revenue"],
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
                cagr_distribution=self._distribution(
                    [item.revenue_cagr for item in companies], (-5, 5, 10, 15, 20, 30)
                ),
                margin_distribution=self._distribution(
                    [item.operating_margin for item in companies], (0, 5, 10, 15, 20, 30)
                ),
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
            loaded = tuple(
                item
                for snapshot in snapshots
                if (item := _base_from_snapshot(snapshot)) is not None
            )
        except (AttributeError, KeyError, ValueError):
            loaded = ()
        real_company_limit = MAX_LEAGUE_COMPANIES - TEMPORARY_COMPANY_COUNT
        return (*loaded[:real_company_limit], *_temporary_bases())

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
        net_debt = base.net_debt
        net_debt_to_revenue = net_debt / max(base.revenues[2025], 1.0) * 100.0
        growth_component = growth_score(cagr)
        profitability_component = profitability_score(margin)
        stability_score = financial_stability_score(
            debt_ratio, net_debt, base.revenues[2025]
        )
        stability_score = _round(stability_score)
        composite = (
            growth_component * 0.35
            + profitability_component * 0.35
            + stability_score * 0.30
        )
        overall_tier = composite_tier(_round(composite))
        historical_margin = margin_by_year[2025]
        historical_growth_score = growth_score(historical_growth * 100)
        historical_profit_score = profitability_score(historical_margin)
        historical_stability = stability_score
        historical_score = (
            historical_growth_score * 0.35
            + historical_profit_score * 0.35
            + historical_stability * 0.30
        )
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
            "growth_score": growth_component,
            "profitability_score": profitability_component,
            "stability_score": _round(stability_score),
            "revenue_cagr": _round(cagr),
            "operating_margin": _round(margin),
            "liabilities_to_assets": _round(debt_ratio),
            "net_debt": _round(net_debt),
            "net_debt_to_revenue": _round(net_debt_to_revenue),
            "tier": overall_tier,
            "candles": candles,
            "historical_score": historical_score,
        }

    @staticmethod
    def _candle(
        year: int, annual_revenue: float, margin: float, evidence_id: str
    ) -> FinancialCandle:
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
    def _distribution(
        values: list[float], edges: tuple[int, ...]
    ) -> tuple[LeagueDistributionBucket, ...]:
        buckets: list[LeagueDistributionBucket] = []
        for low, high in pairwise(edges):
            buckets.append(
                LeagueDistributionBucket(
                    label=f"{low}-{high}%", count=sum(low <= value < high for value in values)
                )
            )
        buckets.append(
            LeagueDistributionBucket(
                label=f"{edges[-1]}%+", count=sum(value >= edges[-1] for value in values)
            )
        )
        return tuple(buckets)


__all__ = [
    "COMPOSITE_TIER_THRESHOLDS",
    "FinancialLeagueService",
    "FinancialLeagueStorePort",
    "GROWTH_SCORE_CEILING",
    "GROWTH_SCORE_FLOOR",
    "MARGIN_SCORE_CEILING",
    "MARGIN_SCORE_FLOOR",
    "TEMPORARY_COMPANY_COUNT",
    "composite_tier",
    "financial_stability_score",
    "growth_score",
    "profitability_score",
]
