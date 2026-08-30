"""Deterministic company-comparison snapshot materialization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from itertools import pairwise
from math import pow
from statistics import fmean
from typing import Final, TypedDict

from backend.features.bi.evidence import verifiable_cells
from backend.features.bi.models import (
    AmountScale,
    AvailableObservation,
    BiDashboardSnapshot,
    BiEvidence,
    CompanyId,
    MetricId,
    SnapshotStatus,
)

from .errors import ComparisonDataError
from .league_scoring import (
    composite_tier,
    financial_stability_score,
    growth_score,
    profitability_score,
)
from .models import (
    CompanyComparisonSnapshot,
    ComparisonAssumption,
    ComparisonCompany,
    ComparisonDistributionBucket,
    ComparisonEvidence,
    ComparisonExclusion,
    ComparisonPeriod,
    ComparisonSnapshotMeta,
    ComparisonSpotlight,
    FinancialTier,
)

SCORING_VERSION: Final = "financial-league-v3"
FORECAST_VERSION: Final = "historical-cagr-hold-v1"
FORECAST_ASSUMPTION_ID: Final = "historical-cagr-hold-v1"
MAX_COMPANIES: Final = 30
MAX_HISTORICAL_PERIODS: Final = 5
FORECAST_PERIODS: Final = 3


@dataclass(frozen=True, slots=True)
class ObservedValue:
    value: float
    evidence: tuple[BiEvidence, ...]


@dataclass(frozen=True, slots=True)
class BaseFinancials:
    company_id: CompanyId
    display_name: str
    currency: str
    scale: AmountScale
    source_snapshot_id: str
    file_name: str
    revenues: dict[int, ObservedValue]
    operating_income: dict[int, ObservedValue]
    liabilities: ObservedValue
    assets: ObservedValue
    net_debt: ObservedValue
    financial_position_year: int


class Candidate(TypedDict):
    base: BaseFinancials
    historical_start_year: int
    historical_end_year: int
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
    periods: tuple[ComparisonPeriod, ...]
    historical_score: float


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


def _series(
    snapshot: BiDashboardSnapshot,
    metric_id: MetricId,
) -> dict[int, AvailableObservation]:
    metric = snapshot.metrics.get(metric_id)
    if metric is None:
        return {}
    return {
        year: observation
        for observation in metric.observations
        if isinstance(observation, AvailableObservation)
        and (year := _year(snapshot, str(observation.period_id))) is not None
    }


def _observed(
    observation: AvailableObservation | None,
) -> ObservedValue | None:
    if observation is None:
        return None
    evidence = verifiable_cells(observation.evidence)
    if not evidence:
        return None
    return ObservedValue(
        value=float(observation.normalized_value),
        evidence=evidence,
    )


def _extract_base(
    snapshot: BiDashboardSnapshot,
) -> tuple[BaseFinancials | None, tuple[str, ...]]:
    reasons: list[str] = []
    revenue_series = snapshot.metrics.get(MetricId.REVENUE)
    revenue_raw = _series(snapshot, MetricId.REVENUE)
    income_raw = _series(snapshot, MetricId.OPERATING_INCOME)
    common_years = sorted(set(revenue_raw) & set(income_raw))[-MAX_HISTORICAL_PERIODS:]
    if len(common_years) < 2:
        reasons.append("매출과 영업이익이 함께 존재하는 회계연도가 2개 미만입니다.")
    if revenue_series is None or revenue_series.currency is None or revenue_series.scale is None:
        reasons.append("매출 통화 또는 배율 정보가 없습니다.")
    else:
        amount_metrics = (
            MetricId.OPERATING_INCOME,
            MetricId.TOTAL_LIABILITIES,
            MetricId.TOTAL_ASSETS,
            MetricId.NET_DEBT,
        )
        for metric_id in amount_metrics:
            series = snapshot.metrics.get(metric_id)
            if series is not None and (
                series.currency != revenue_series.currency or series.scale != revenue_series.scale
            ):
                reasons.append("비교에 사용하는 금액 지표의 통화 또는 배율이 일치하지 않습니다.")
                break

    revenues: dict[int, ObservedValue] = {}
    operating_income: dict[int, ObservedValue] = {}
    for year in common_years:
        revenue = _observed(revenue_raw[year])
        income = _observed(income_raw[year])
        if revenue is None or income is None:
            reasons.append(f"{year}년 매출 또는 영업이익의 원본 셀 근거가 없습니다.")
            continue
        if revenue.value <= 0:
            reasons.append(f"{year}년 매출이 0 이하라 비교 지표를 계산할 수 없습니다.")
            continue
        revenues[year] = revenue
        operating_income[year] = income

    latest_year = max(revenues) if revenues else None
    liabilities = _observed(
        _series(snapshot, MetricId.TOTAL_LIABILITIES).get(latest_year)
        if latest_year is not None
        else None
    )
    assets = _observed(
        _series(snapshot, MetricId.TOTAL_ASSETS).get(latest_year)
        if latest_year is not None
        else None
    )
    net_debt = _observed(
        _series(snapshot, MetricId.NET_DEBT).get(latest_year) if latest_year is not None else None
    )
    if liabilities is None:
        reasons.append("비교 기준 회계연도의 총부채 값 또는 원본 셀 근거가 없습니다.")
    if assets is None or assets.value <= 0:
        reasons.append("비교 기준 회계연도의 유효한 총자산 값과 원본 셀 근거가 없습니다.")
    if net_debt is None:
        reasons.append("비교 기준 회계연도의 순부채 값 또는 원본 셀 근거가 없습니다.")
    if len(revenues) < 2:
        reasons.append("검증 가능한 비교 회계연도가 2개 미만입니다.")

    unique_reasons = tuple(dict.fromkeys(reasons))
    if unique_reasons:
        return None, unique_reasons
    assert revenue_series is not None
    assert revenue_series.currency is not None
    assert revenue_series.scale is not None
    assert liabilities is not None and assets is not None and net_debt is not None
    assert latest_year is not None
    return (
        BaseFinancials(
            company_id=snapshot.company.company_id,
            display_name=snapshot.company.display_name,
            currency=revenue_series.currency,
            scale=revenue_series.scale,
            source_snapshot_id=str(snapshot.snapshot.snapshot_id),
            file_name=snapshot.source.file_name,
            revenues=revenues,
            operating_income=operating_income,
            liabilities=liabilities,
            assets=assets,
            net_debt=net_debt,
            financial_position_year=latest_year,
        ),
        (),
    )


class EvidenceRegistry:
    def __init__(self) -> None:
        self._ids: dict[tuple[str, str, int | None, str], str] = {}
        self._items: list[ComparisonEvidence] = []

    @property
    def items(self) -> tuple[ComparisonEvidence, ...]:
        return tuple(self._items)

    def register(
        self,
        *,
        base: BaseFinancials,
        metric_id: MetricId,
        year: int | None,
        observed: ObservedValue,
    ) -> tuple[str, ...]:
        registered: list[str] = []
        for source_evidence in observed.evidence:
            key = (
                str(base.company_id),
                metric_id.value,
                year,
                source_evidence.cell_id,
            )
            evidence_id = self._ids.get(key)
            if evidence_id is None:
                evidence_id = f"E{len(self._items) + 1}"
                self._ids[key] = evidence_id
                self._items.append(
                    ComparisonEvidence(
                        evidence_id=evidence_id,
                        company_id=base.company_id,
                        metric_id=metric_id,
                        year=year,
                        file_name=base.file_name,
                        sheet_name=source_evidence.sheet_name,
                        cell_coord=source_evidence.cell_coord,
                        source_text=source_evidence.source_text,
                    )
                )
            registered.append(evidence_id)
        return tuple(registered)


class CompanyComparisonSnapshotBuilder:
    """Build a comparison snapshot using only audited BI observations."""

    @staticmethod
    def source_fingerprint(snapshots: tuple[BiDashboardSnapshot, ...]) -> str:
        source = "|".join(sorted(str(snapshot.snapshot.snapshot_id) for snapshot in snapshots))
        return sha256(source.encode("utf-8")).hexdigest()

    def build(
        self,
        snapshots: tuple[BiDashboardSnapshot, ...],
        *,
        generated_at: datetime | None = None,
    ) -> CompanyComparisonSnapshot:
        ordered = tuple(
            sorted(
                snapshots,
                key=lambda item: (
                    item.company.display_name.casefold(),
                    str(item.company.company_id),
                ),
            )[:MAX_COMPANIES]
        )
        bases: list[BaseFinancials] = []
        exclusions: list[ComparisonExclusion] = []
        for snapshot in ordered:
            base, reasons = _extract_base(snapshot)
            if base is not None:
                bases.append(base)
            else:
                exclusions.append(
                    ComparisonExclusion(
                        company_id=snapshot.company.company_id,
                        display_name=snapshot.company.display_name,
                        reasons=reasons,
                    )
                )
        if len(bases) < 2:
            raise ComparisonDataError(
                "comparison_snapshot_insufficient_companies",
                "기업 비교 스냅샷에는 근거가 완전한 기업이 최소 2개 필요합니다. "
                f"현재 {len(bases)}개입니다.",
            )

        evidence = EvidenceRegistry()
        candidates = tuple(self._candidate(base, evidence) for base in bases)
        previous_order = sorted(
            candidates,
            key=lambda item: item["historical_score"],
            reverse=True,
        )
        previous_rank = self._competition_ranks(
            previous_order,
            lambda item: item["historical_score"],
        )
        current_order = sorted(
            candidates,
            key=lambda item: item["composite_score"],
            reverse=True,
        )
        current_rank = self._competition_ranks(
            current_order,
            lambda item: item["composite_score"],
        )
        companies = tuple(
            ComparisonCompany(
                company_id=item["base"].company_id,
                display_name=item["base"].display_name,
                currency=item["base"].currency,
                scale=item["base"].scale,
                source_snapshot_id=item["base"].source_snapshot_id,
                historical_start_year=item["historical_start_year"],
                historical_end_year=item["historical_end_year"],
                rank=current_rank[str(item["base"].company_id)],
                previous_rank=previous_rank[str(item["base"].company_id)],
                rank_change=(
                    previous_rank[str(item["base"].company_id)]
                    - current_rank[str(item["base"].company_id)]
                ),
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
                periods=item["periods"],
            )
            for item in current_order
        )
        now = generated_at or datetime.now(timezone.utc)
        fingerprint = self.source_fingerprint(ordered)
        snapshot_digest = sha256(
            f"{fingerprint}|{SCORING_VERSION}|{FORECAST_VERSION}".encode("utf-8")
        ).hexdigest()
        riser = max(companies, key=lambda item: (item.rank_change, item.composite_score))
        return CompanyComparisonSnapshot(
            snapshot=ComparisonSnapshotMeta(
                snapshot_id=f"comparison-{snapshot_digest[:24]}",
                status=(SnapshotStatus.PARTIAL if exclusions else SnapshotStatus.READY),
                generated_at=now,
                source_fingerprint=fingerprint,
                source_snapshot_ids=tuple(base.source_snapshot_id for base in bases),
                scoring_version=SCORING_VERSION,
                forecast_version=FORECAST_VERSION,
            ),
            historical_start_year=min(item.historical_start_year for item in companies),
            historical_end_year=max(item.historical_end_year for item in companies),
            forecast_end_year=max(
                period.year
                for item in companies
                for period in item.periods
                if period.period_type == "forecast"
            ),
            companies=companies,
            spotlight=ComparisonSpotlight(
                leader_company_id=companies[0].company_id,
                riser_company_id=riser.company_id,
                average_cagr=_round(fmean(item.revenue_cagr for item in companies)),
                average_margin=_round(fmean(item.operating_margin for item in companies)),
                average_liabilities_to_assets=_round(
                    fmean(item.liabilities_to_assets for item in companies)
                ),
                cagr_distribution=self._distribution(
                    [item.revenue_cagr for item in companies],
                    (-5, 5, 10, 15, 20, 30),
                ),
                margin_distribution=self._distribution(
                    [item.operating_margin for item in companies],
                    (0, 5, 10, 15, 20, 30),
                ),
            ),
            evidence=evidence.items,
            exclusions=tuple(exclusions),
            assumptions=(
                ComparisonAssumption(
                    assumption_id=FORECAST_ASSUMPTION_ID,
                    description=(
                        "향후 3개년 매출은 각 기업의 실제 관측 구간 CAGR을 -12%~30%로 "
                        "제한해 적용하고, 영업이익률은 최근 실제 연도 수준을 유지합니다. "
                        "예측값은 순위 점수 계산에 사용하지 않습니다."
                    ),
                ),
            ),
        )

    def _candidate(
        self,
        base: BaseFinancials,
        evidence: EvidenceRegistry,
    ) -> Candidate:
        years = sorted(base.revenues)
        first_year, last_year = years[0], years[-1]
        span = last_year - first_year
        historical_growth = (
            pow(
                base.revenues[last_year].value / base.revenues[first_year].value,
                1 / span,
            )
            - 1
        )
        latest_margin = (
            base.operating_income[last_year].value / base.revenues[last_year].value * 100
        )
        debt_ratio = base.liabilities.value / base.assets.value * 100
        net_debt_to_revenue = base.net_debt.value / base.revenues[last_year].value * 100
        growth_component = growth_score(historical_growth * 100)
        profitability_component = profitability_score(latest_margin)
        stability_component = financial_stability_score(
            debt_ratio,
            base.net_debt.value,
            base.revenues[last_year].value,
        )
        composite = _round(
            growth_component * 0.35 + profitability_component * 0.35 + stability_component * 0.30
        )

        periods: list[ComparisonPeriod] = []
        for year in years:
            revenue_evidence = evidence.register(
                base=base,
                metric_id=MetricId.REVENUE,
                year=year,
                observed=base.revenues[year],
            )
            income_evidence = evidence.register(
                base=base,
                metric_id=MetricId.OPERATING_INCOME,
                year=year,
                observed=base.operating_income[year],
            )
            periods.append(
                ComparisonPeriod(
                    year=year,
                    period_type="historical",
                    revenue=_round(base.revenues[year].value),
                    operating_income=_round(base.operating_income[year].value),
                    operating_margin=_round(
                        base.operating_income[year].value / base.revenues[year].value * 100
                    ),
                    evidence_ids=tuple(dict.fromkeys(revenue_evidence + income_evidence)),
                )
            )

        forecast_basis = tuple(
            dict.fromkeys(
                evidence.register(
                    base=base,
                    metric_id=MetricId.REVENUE,
                    year=first_year,
                    observed=base.revenues[first_year],
                )
                + evidence.register(
                    base=base,
                    metric_id=MetricId.REVENUE,
                    year=last_year,
                    observed=base.revenues[last_year],
                )
                + evidence.register(
                    base=base,
                    metric_id=MetricId.OPERATING_INCOME,
                    year=last_year,
                    observed=base.operating_income[last_year],
                )
            )
        )
        forecast_growth = min(0.30, max(-0.12, historical_growth))
        forecast_revenue = base.revenues[last_year].value
        for year in range(last_year + 1, last_year + FORECAST_PERIODS + 1):
            forecast_revenue *= 1 + forecast_growth
            periods.append(
                ComparisonPeriod(
                    year=year,
                    period_type="forecast",
                    revenue=_round(forecast_revenue),
                    operating_income=_round(forecast_revenue * latest_margin / 100),
                    operating_margin=_round(latest_margin),
                    evidence_ids=forecast_basis,
                    assumption_id=FORECAST_ASSUMPTION_ID,
                )
            )

        for metric_id, observed in (
            (MetricId.TOTAL_LIABILITIES, base.liabilities),
            (MetricId.TOTAL_ASSETS, base.assets),
            (MetricId.NET_DEBT, base.net_debt),
        ):
            evidence.register(
                base=base,
                metric_id=metric_id,
                year=base.financial_position_year,
                observed=observed,
            )

        if len(years) >= 3:
            previous_end = years[-2]
            previous_span = previous_end - first_year
            previous_growth = (
                pow(
                    base.revenues[previous_end].value / base.revenues[first_year].value,
                    1 / previous_span,
                )
                - 1
            )
            previous_margin = (
                base.operating_income[previous_end].value / base.revenues[previous_end].value * 100
            )
            historical_score = (
                growth_score(previous_growth * 100) * 0.35
                + profitability_score(previous_margin) * 0.35
                + financial_stability_score(
                    debt_ratio,
                    base.net_debt.value,
                    base.revenues[previous_end].value,
                )
                * 0.30
            )
        else:
            historical_score = composite

        return {
            "base": base,
            "historical_start_year": first_year,
            "historical_end_year": last_year,
            "composite_score": composite,
            "growth_score": growth_component,
            "profitability_score": profitability_component,
            "stability_score": stability_component,
            "revenue_cagr": _round(historical_growth * 100),
            "operating_margin": _round(latest_margin),
            "liabilities_to_assets": _round(debt_ratio),
            "net_debt": _round(base.net_debt.value),
            "net_debt_to_revenue": _round(net_debt_to_revenue),
            "tier": composite_tier(composite),
            "periods": tuple(periods),
            "historical_score": historical_score,
        }

    @staticmethod
    def _competition_ranks(
        ordered: list[Candidate],
        score: Callable[[Candidate], float],
    ) -> dict[str, int]:
        ranks: dict[str, int] = {}
        previous_score: float | None = None
        current_rank = 0
        for position, item in enumerate(ordered, 1):
            item_score = score(item)
            if previous_score is None or item_score != previous_score:
                current_rank = position
                previous_score = item_score
            ranks[str(item["base"].company_id)] = current_rank
        return ranks

    @staticmethod
    def _distribution(
        values: list[float],
        edges: tuple[int, ...],
    ) -> tuple[ComparisonDistributionBucket, ...]:
        buckets = [
            ComparisonDistributionBucket(
                label=f"<{edges[0]}%",
                count=sum(value < edges[0] for value in values),
            ),
            *(
                ComparisonDistributionBucket(
                    label=f"{low}-{high}%",
                    count=sum(low <= value < high for value in values),
                )
                for low, high in pairwise(edges)
            ),
        ]
        buckets.append(
            ComparisonDistributionBucket(
                label=f"{edges[-1]}%+",
                count=sum(value >= edges[-1] for value in values),
            )
        )
        return tuple(buckets)


__all__ = [
    "FORECAST_VERSION",
    "SCORING_VERSION",
    "BaseFinancials",
    "CompanyComparisonSnapshotBuilder",
]
