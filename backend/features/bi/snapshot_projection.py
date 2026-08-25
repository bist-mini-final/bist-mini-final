from dataclasses import dataclass
from datetime import datetime

from .current_periods import select_current_periods
from .extraction_models import BiMetricExtractionResult
from .materialization_models import BiSnapshotBuildInput, BiSnapshotRefreshInput
from .models import (
    AmountScale,
    BiMaterializationRequest,
    BiPeriod,
    JobId,
    MetricId,
)


@dataclass(frozen=True, slots=True)
class BiSnapshotProjection:
    request: BiMaterializationRequest
    job_id: JobId
    periods: tuple[BiPeriod, ...]
    currency: str | None
    scale: AmountScale | None
    extracted: tuple[BiMetricExtractionResult, ...]
    generated_at: datetime


def project_build_input(build_input: BiSnapshotBuildInput) -> BiSnapshotProjection:
    return BiSnapshotProjection(
        request=build_input.request,
        job_id=build_input.job_id,
        periods=select_current_periods(
            build_input.profile.periods,
            build_input.generated_at,
        ),
        currency=build_input.profile.currency,
        scale=build_input.profile.scale,
        extracted=build_input.extracted,
        generated_at=build_input.generated_at,
    )


def project_refresh_input(
    refresh_input: BiSnapshotRefreshInput,
) -> BiSnapshotProjection:
    base = refresh_input.base_snapshot
    amount_series = base.metrics[MetricId.REVENUE]
    profile = refresh_input.profile
    return BiSnapshotProjection(
        request=BiMaterializationRequest(
            company_id=base.company.company_id,
            display_name=base.company.display_name,
            source=base.source,
        ),
        job_id=refresh_input.job_id,
        periods=select_current_periods(base.periods, refresh_input.generated_at),
        currency=(
            profile.currency
            if profile is not None and profile.currency is not None
            else amount_series.currency
        ),
        scale=(
            profile.scale
            if profile is not None and profile.scale is not None
            else amount_series.scale
        ),
        extracted=refresh_input.extracted,
        generated_at=refresh_input.generated_at,
    )
