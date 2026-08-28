from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Mapping

from backend.features.bi.calendar_periods import (
    CalendarQuarter,
    index_fiscal_periods_by_calendar_year,
)
from backend.features.bi.models import (
    AvailableObservation,
    BiDashboardSnapshot,
    BiEvidence,
    BiPeriod,
    MetricId,
)

from .models import ComparisonCompanyResult, ComparisonPoint


class ComparisonDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SnapshotEvidenceItem:
    company_id: str
    file_name: str
    evidence: BiEvidence
    origin: Literal["snapshot", "rag"] = "snapshot"


@dataclass(frozen=True, slots=True)
class ComparisonObservation:
    normalized_value: Decimal
    evidence: tuple[BiEvidence, ...]
    origin: Literal["snapshot", "rag"] = "snapshot"


@dataclass(frozen=True, slots=True)
class CompanyForecastData:
    company_id: str
    observations: Mapping[int, Mapping[MetricId, ComparisonObservation]]


@dataclass(frozen=True, slots=True)
class CalculatedComparison:
    companies: tuple[ComparisonCompanyResult, ...]
    evidence: tuple[SnapshotEvidenceItem, ...]
    stability_basis_year: int
    alignment_warnings: tuple[str, ...] = ()


def _period_by_year(snapshot: BiDashboardSnapshot) -> dict[int, BiPeriod]:
    return {
        year: normalized.source
        for year, normalized in index_fiscal_periods_by_calendar_year(
            snapshot.periods
        ).items()
    }


def _calendar_alignment_warnings(
    snapshots: tuple[BiDashboardSnapshot, ...],
    selected_years: tuple[int, ...],
) -> tuple[str, ...]:
    alignments = {
        str(snapshot.company.company_id): index_fiscal_periods_by_calendar_year(
            snapshot.periods
        )
        for snapshot in snapshots
    }
    warnings: list[str] = []
    for year in selected_years:
        company_axes: list[str] = []
        quarters: set[CalendarQuarter] = set()
        for snapshot in snapshots:
            normalized = alignments[str(snapshot.company.company_id)].get(year)
            if normalized is None or normalized.calendar_period.quarter is None:
                continue
            quarters.add(normalized.calendar_period.quarter)
            company_axes.append(
                f"{snapshot.company.display_name}={normalized.calendar_period.axis_label}"
            )
        if len(quarters) > 1:
            warnings.append(
                f"{year}년 회계기간은 글로벌 달력 분기로 정규화했으며 결산 시점이 "
                f"서로 다릅니다 ({', '.join(company_axes)})."
            )
    return tuple(warnings)


def _available(
    snapshot: BiDashboardSnapshot,
    metric_id: MetricId,
    year: int,
) -> ComparisonObservation:
    period = _period_by_year(snapshot).get(year)
    series = snapshot.metrics.get(metric_id)
    if period is None or series is None:
        raise ComparisonDataError(
            "comparison_data_incomplete",
            f"{snapshot.company.display_name}의 {year}년 {metric_id.value} 지표가 없습니다.",
        )
    observation = next(
        (item for item in series.observations if item.period_id == period.period_id),
        None,
    )
    if not isinstance(observation, AvailableObservation):
        raise ComparisonDataError(
            "comparison_data_incomplete",
            f"{snapshot.company.display_name}의 {year}년 {metric_id.value} 지표를 사용할 수 없습니다.",
        )
    return ComparisonObservation(
        normalized_value=observation.normalized_value,
        evidence=observation.evidence,
    )


def _comparison_value(
    snapshot: BiDashboardSnapshot,
    metric_id: MetricId,
    year: int,
    forecasts: Mapping[str, CompanyForecastData],
) -> ComparisonObservation:
    forecast = forecasts.get(str(snapshot.company.company_id))
    if forecast is not None:
        observation = forecast.observations.get(year, {}).get(metric_id)
        if observation is not None:
            return observation
    return _available(snapshot, metric_id, year)


def _percent(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.0001")))


def calculate_comparison(
    snapshots: tuple[BiDashboardSnapshot, ...],
    start_year: int,
    end_year: int,
    forecast_data: tuple[CompanyForecastData, ...] = (),
) -> CalculatedComparison:
    if len(snapshots) < 2 or len(snapshots) > 3:
        raise ComparisonDataError(
            "comparison_company_count_invalid",
            "기업 비교에는 2개 이상 3개 이하의 기업이 필요합니다.",
        )

    forecasts = {item.company_id: item for item in forecast_data}

    def company_years(snapshot: BiDashboardSnapshot) -> set[int]:
        years = set(_period_by_year(snapshot))
        forecast = forecasts.get(str(snapshot.company.company_id))
        if forecast is not None:
            years.update(forecast.observations)
        return years

    common_years = company_years(snapshots[0])
    for snapshot in snapshots[1:]:
        common_years.intersection_update(company_years(snapshot))
    selected_years = tuple(
        year for year in sorted(common_years) if start_year <= year <= end_year
    )
    if start_year not in common_years or end_year not in common_years:
        raise ComparisonDataError(
            "comparison_data_incomplete",
            "선택한 기업에 공통으로 존재하는 시작·종료 회계연도가 아닙니다.",
        )
    if len(selected_years) < 2:
        raise ComparisonDataError(
            "comparison_data_incomplete",
            "비교 기간에는 공통 회계연도가 최소 2개 필요합니다.",
        )

    historical_common_years = set(_period_by_year(snapshots[0]))
    for snapshot in snapshots[1:]:
        historical_common_years.intersection_update(_period_by_year(snapshot))
    stability_candidates = [year for year in historical_common_years if year <= end_year]
    if not stability_candidates:
        raise ComparisonDataError(
            "comparison_data_incomplete",
            "선택한 기간 이전의 공통 재무상태표 기준연도가 없습니다.",
        )
    stability_basis_year = max(stability_candidates)

    results: list[ComparisonCompanyResult] = []
    evidence_items: list[SnapshotEvidenceItem] = []
    for snapshot in snapshots:
        start_revenue = _comparison_value(
            snapshot, MetricId.REVENUE, start_year, forecasts
        )
        end_revenue = _comparison_value(
            snapshot, MetricId.REVENUE, end_year, forecasts
        )
        end_operating_income = _comparison_value(
            snapshot, MetricId.OPERATING_INCOME, end_year, forecasts
        )
        total_liabilities = _available(
            snapshot, MetricId.TOTAL_LIABILITIES, stability_basis_year
        )
        total_assets = _available(
            snapshot, MetricId.TOTAL_ASSETS, stability_basis_year
        )
        net_debt = _available(snapshot, MetricId.NET_DEBT, stability_basis_year)
        if (
            start_revenue.normalized_value <= 0
            or end_revenue.normalized_value <= 0
            or total_assets.normalized_value <= 0
        ):
            raise ComparisonDataError(
                "comparison_data_incomplete",
                f"{snapshot.company.display_name}의 계산 기준값이 0 이하입니다.",
            )

        points: list[ComparisonPoint] = []
        used_observations: list[ComparisonObservation] = [
            start_revenue,
            end_revenue,
            end_operating_income,
            total_liabilities,
            total_assets,
            net_debt,
        ]
        for year in selected_years:
            revenue = _comparison_value(
                snapshot, MetricId.REVENUE, year, forecasts
            )
            operating_income = _comparison_value(
                snapshot, MetricId.OPERATING_INCOME, year, forecasts
            )
            used_observations.extend((revenue, operating_income))
            points.append(
                ComparisonPoint(
                    year=year,
                    revenue=float(revenue.normalized_value),
                    operating_income=float(operating_income.normalized_value),
                )
            )

        year_gap = end_year - start_year
        revenue_ratio = end_revenue.normalized_value / start_revenue.normalized_value
        revenue_cagr = (
            Decimal(str(float(revenue_ratio) ** (1 / year_gap))) - Decimal(1)
        ) * 100
        operating_margin = (
            end_operating_income.normalized_value / end_revenue.normalized_value
        ) * 100
        liabilities_to_assets = (
            total_liabilities.normalized_value / total_assets.normalized_value
        ) * 100
        revenue_series = snapshot.metrics[MetricId.REVENUE]
        if revenue_series.currency is None or revenue_series.scale is None:
            raise ComparisonDataError(
                "comparison_data_incomplete",
                f"{snapshot.company.display_name}의 매출 단위가 없습니다.",
            )
        results.append(
            ComparisonCompanyResult(
                company_id=snapshot.company.company_id,
                display_name=snapshot.company.display_name,
                currency=revenue_series.currency,
                scale=revenue_series.scale,
                points=tuple(points),
                revenue_cagr=_percent(revenue_cagr),
                operating_margin=_percent(operating_margin),
                liabilities_to_assets=_percent(liabilities_to_assets),
                net_debt=float(net_debt.normalized_value),
                stability_basis_year=stability_basis_year,
            )
        )

        seen: set[str] = set()
        for observation in used_observations:
            for item in observation.evidence:
                key = f"{snapshot.company.company_id}:{item.cell_id}"
                if key in seen:
                    continue
                seen.add(key)
                evidence_items.append(
                    SnapshotEvidenceItem(
                        company_id=str(snapshot.company.company_id),
                        file_name=snapshot.source.file_name,
                        evidence=item,
                        origin=observation.origin,
                    )
                )

    return CalculatedComparison(
        tuple(results),
        tuple(evidence_items),
        stability_basis_year,
        _calendar_alignment_warnings(snapshots, selected_years),
    )


__all__ = [
    "CalculatedComparison",
    "CompanyForecastData",
    "ComparisonObservation",
    "ComparisonDataError",
    "SnapshotEvidenceItem",
    "calculate_comparison",
]
