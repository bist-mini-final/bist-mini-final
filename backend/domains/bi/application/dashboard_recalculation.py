"""BI dashboard recalculation use case."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.domains.bi.domain.catalog import METRIC_CATALOG, SourceMetricDefinition
from backend.domains.bi.domain.extraction_models import BiMetricExtractionResult
from backend.domains.bi.domain.materialization_models import BiSnapshotRefreshInput
from backend.domains.bi.domain.models import (
    BiDashboardSnapshot,
    CompanyId,
    JobId,
    MetricId,
    PeriodId,
)

from .snapshot_builder import BiSnapshotBuilder


class BiDashboardRecalculationStore(Protocol):
    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None: ...

    def publish(self, snapshot: BiDashboardSnapshot) -> None: ...


@dataclass(frozen=True, slots=True)
class BiDashboardRecalculationError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"BI dashboard recalculation failed: {self.reason}"


def _source_results(
    snapshot: BiDashboardSnapshot,
) -> tuple[BiMetricExtractionResult, ...]:
    results: list[BiMetricExtractionResult] = []
    for metric_id, definition in METRIC_CATALOG.items():
        if not isinstance(definition, SourceMetricDefinition):
            continue
        series = snapshot.metrics.get(metric_id)
        if series is None:
            raise BiDashboardRecalculationError(
                f"source metric is unavailable: {metric_id.value}"
            )
        observations = {
            observation.period_id: observation
            for observation in series.observations
        }
        for period in snapshot.periods:
            observation = observations.get(period.period_id)
            if observation is None:
                raise BiDashboardRecalculationError(
                    "source observation is unavailable: "
                    f"{metric_id.value}/{period.period_id}"
                )
            results.append(
                BiMetricExtractionResult(
                    metric_id=MetricId(metric_id),
                    period_id=PeriodId(period.period_id),
                    value_kind=series.value_kind,
                    currency=series.currency,
                    scale=series.scale,
                    observation=observation,
                )
            )
    return tuple(results)


def recalculate_dashboard(
    *,
    store: BiDashboardRecalculationStore,
    company_id: CompanyId,
    job_id: JobId,
    generated_at: datetime,
) -> BiDashboardSnapshot:
    base = store.get_current(company_id)
    if base is None:
        raise BiDashboardRecalculationError("current snapshot is unavailable")
    refreshed = BiSnapshotBuilder().refresh(
        BiSnapshotRefreshInput(
            base_snapshot=base,
            job_id=job_id,
            extracted=_source_results(base),
            generated_at=generated_at,
        )
    )
    store.publish(refreshed)
    return refreshed
