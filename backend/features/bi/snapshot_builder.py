from hashlib import sha256
from typing import Final, assert_never

from backend.domains.bi.domain.catalog import (
    CATALOG_VERSION,
    FORMULA_VERSION,
    METRIC_CATALOG,
    DerivedMetricDefinition,
    MetricDisplayRole,
    SourceMetricDefinition,
)
from backend.domains.bi.domain.materialization_models import (
    BiSnapshotBuildInput,
    BiSnapshotRefreshInput,
)
from backend.domains.bi.domain.models import (
    BiCompany,
    BiDashboardSnapshot,
    BiIssue,
    BiRefreshState,
    BiSnapshotMeta,
    MetricId,
    MetricObservation,
    MetricSeries,
    MetricStatus,
    PeriodId,
    PeriodKind,
    RefreshStatus,
    SnapshotId,
    SnapshotStatus,
    UnavailableObservation,
    ValueKind,
)

from .calculator import (
    DebtComponents,
    calculate_debt_ratio,
    calculate_free_cash_flow,
    calculate_free_cash_flow_margin,
    calculate_net_debt,
    calculate_net_debt_ratio,
    calculate_net_margin,
    calculate_operating_margin,
    calculate_revenue_yoy_growth,
    calculate_total_debt,
)
from .snapshot_projection import (
    BiSnapshotProjection,
    project_build_input,
    project_refresh_input,
)

SERIES_STATUS_PRIORITY: Final = (
    MetricStatus.INVALID,
    MetricStatus.AMBIGUOUS,
    MetricStatus.MISSING,
    MetricStatus.NOT_MEANINGFUL,
)


def _unavailable(period_id: PeriodId, reason: str) -> UnavailableObservation:
    return UnavailableObservation(
        period_id=period_id,
        status=MetricStatus.NOT_MEANINGFUL,
        reason=reason,
    )


def _series_status(
    observations: tuple[MetricObservation, ...],
) -> MetricStatus:
    if any(item.status is MetricStatus.AVAILABLE for item in observations):
        return MetricStatus.AVAILABLE
    for status in SERIES_STATUS_PRIORITY:
        if any(item.status is status for item in observations):
            return status
    return MetricStatus.MISSING


class BiSnapshotBuilder:
    def build(self, build_input: BiSnapshotBuildInput) -> BiDashboardSnapshot:
        return self._assemble(project_build_input(build_input))

    def refresh(self, refresh_input: BiSnapshotRefreshInput) -> BiDashboardSnapshot:
        return self._assemble(project_refresh_input(refresh_input))

    def _assemble(
        self,
        projection: BiSnapshotProjection,
    ) -> BiDashboardSnapshot:
        extracted = {
            (result.metric_id, result.period_id): result
            for result in projection.extracted
        }
        observations: dict[MetricId, dict[PeriodId, MetricObservation]] = {
            metric_id: {} for metric_id in MetricId
        }
        for metric_id, definition in METRIC_CATALOG.items():
            match definition:
                case SourceMetricDefinition():
                    for period in projection.periods:
                        observations[metric_id][period.period_id] = extracted[
                            (metric_id, period.period_id)
                        ].observation
                case DerivedMetricDefinition():
                    continue
                case _:
                    raise TypeError(
                        f"지원하지 않는 BI metric definition: {type(definition).__name__}"
                    )

        for period in projection.periods:
            period_id = period.period_id
            observations[MetricId.TOTAL_DEBT][period_id] = calculate_total_debt(
                observations[MetricId.TOTAL_DEBT][period_id],
                DebtComponents(
                    short_term_debt=observations[MetricId.SHORT_TERM_DEBT][period_id],
                    current_portion_of_long_term_debt=observations[
                        MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT
                    ][period_id],
                    long_term_debt=observations[MetricId.LONG_TERM_DEBT][period_id],
                ),
            )
            observations[MetricId.OPERATING_MARGIN][period_id] = (
                calculate_operating_margin(
                    observations[MetricId.OPERATING_INCOME][period_id],
                    observations[MetricId.REVENUE][period_id],
                )
            )
            observations[MetricId.NET_MARGIN][period_id] = calculate_net_margin(
                observations[MetricId.NET_INCOME][period_id],
                observations[MetricId.REVENUE][period_id],
            )
            observations[MetricId.FREE_CASH_FLOW][period_id] = (
                calculate_free_cash_flow(
                    observations[MetricId.OPERATING_CASH_FLOW][period_id],
                    observations[MetricId.CAPITAL_EXPENDITURE][period_id],
                )
            )
            observations[MetricId.NET_DEBT][period_id] = calculate_net_debt(
                observations[MetricId.TOTAL_DEBT][period_id],
                observations[MetricId.CASH_AND_SHORT_TERM_INVESTMENTS][period_id],
            )
            observations[MetricId.FREE_CASH_FLOW_MARGIN][period_id] = (
                calculate_free_cash_flow_margin(
                    observations[MetricId.FREE_CASH_FLOW][period_id],
                    observations[MetricId.REVENUE][period_id],
                )
            )
            observations[MetricId.DEBT_RATIO][period_id] = calculate_debt_ratio(
                observations[MetricId.TOTAL_LIABILITIES][period_id],
                observations[MetricId.TOTAL_ASSETS][period_id],
            )
            observations[MetricId.NET_DEBT_RATIO][period_id] = (
                calculate_net_debt_ratio(
                    observations[MetricId.NET_DEBT][period_id],
                    observations[MetricId.TOTAL_ASSETS][period_id],
                )
            )

        previous_fy: MetricObservation | None = None
        for period in projection.periods:
            revenue = observations[MetricId.REVENUE][period.period_id]
            match period.kind:
                case PeriodKind.FY:
                    growth = (
                        _unavailable(period.period_id, "comparable_prior_period_missing")
                        if previous_fy is None
                        else calculate_revenue_yoy_growth(revenue, previous_fy)
                    )
                    previous_fy = revenue
                case PeriodKind.LTM:
                    growth = _unavailable(
                        period.period_id,
                        "comparable_prior_ltm_missing",
                    )
                case unreachable:
                    assert_never(unreachable)
            observations[MetricId.REVENUE_YOY_GROWTH][period.period_id] = growth

        metrics: dict[MetricId, MetricSeries] = {}
        issues: list[BiIssue] = []
        for metric_id, definition in METRIC_CATALOG.items():
            ordered = tuple(
                observations[metric_id][period.period_id]
                for period in projection.periods
            )
            status = _series_status(ordered)
            currency = (
                projection.currency
                if definition.value_kind is ValueKind.AMOUNT
                else None
            )
            scale = (
                projection.scale
                if definition.value_kind is ValueKind.AMOUNT
                else None
            )
            metrics[metric_id] = MetricSeries(
                metric_id=metric_id,
                label=definition.label_ko,
                value_kind=definition.value_kind,
                currency=currency,
                scale=scale,
                status=status,
                observations=ordered,
            )
            if (
                definition.display_role is MetricDisplayRole.PRIMARY
                and status is not MetricStatus.AVAILABLE
            ):
                issues.append(
                    BiIssue(
                        code="metric_unavailable",
                        message=f"{definition.label_ko} 지표를 사용할 수 없습니다.",
                        metric_id=metric_id,
                    )
                )

        snapshot_status = SnapshotStatus.PARTIAL if issues else SnapshotStatus.READY
        identity = ":".join(
            (
                str(projection.request.company_id),
                projection.request.source.workbook_hash,
                str(projection.job_id),
                CATALOG_VERSION,
                FORMULA_VERSION,
            )
        )
        snapshot_id = SnapshotId(
            "snapshot-" + sha256(identity.encode("utf-8")).hexdigest()[:24]
        )
        return BiDashboardSnapshot(
            schema_version=1,
            company=BiCompany(
                company_id=projection.request.company_id,
                display_name=projection.request.display_name,
            ),
            source=projection.request.source,
            snapshot=BiSnapshotMeta(
                snapshot_id=snapshot_id,
                workbook_hash=projection.request.source.workbook_hash,
                status=snapshot_status,
                generated_at=projection.generated_at,
                catalog_version=CATALOG_VERSION,
                formula_version=FORMULA_VERSION,
            ),
            refresh=BiRefreshState(
                status=RefreshStatus.IDLE,
                job_id=projection.job_id,
                started_at=projection.generated_at,
            ),
            periods=projection.periods,
            metrics=metrics,
            issues=tuple(issues),
        )
