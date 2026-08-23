from dataclasses import dataclass
from datetime import datetime

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from .extraction_models import BiMetricExtractionResult
from .models import (
    AmountScale,
    BiCompany,
    BiContractModel,
    BiDashboardSnapshot,
    BiEvidence,
    BiMaterializationJob,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    JobId,
    SnapshotId,
)


class BiDocumentProfile(BiContractModel):
    periods: tuple[BiPeriod, ...] = Field(min_length=1)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    scale: AmountScale | None = None
    relevant_sheets: tuple[str, ...] = ()
    evidence: tuple[BiEvidence, ...] = ()

    @field_validator("periods")
    @classmethod
    def require_unique_periods(
        cls,
        periods: tuple[BiPeriod, ...],
    ) -> tuple[BiPeriod, ...]:
        ids = {period.period_id for period in periods}
        ordinals = {period.ordinal for period in periods}
        if len(ids) != len(periods) or len(ordinals) != len(periods):
            raise PydanticCustomError(
                "duplicate_period",
                "period_id and ordinal must be unique",
            )
        return tuple(sorted(periods, key=lambda period: period.ordinal))


@dataclass(frozen=True, slots=True)
class BiProfilingFailure:
    code: str
    message: str


BiProfilingResult = BiDocumentProfile | BiProfilingFailure


class BiMaterializationOutcome(BiContractModel):
    job: BiMaterializationJob
    snapshot: BiDashboardSnapshot | None


@dataclass(frozen=True, slots=True)
class BiSnapshotBuildInput:
    request: BiMaterializationRequest
    job_id: JobId
    profile: BiDocumentProfile
    extracted: tuple[BiMetricExtractionResult, ...]
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class BiSnapshotRefreshInput:
    base_snapshot: BiDashboardSnapshot
    job_id: JobId
    extracted: tuple[BiMetricExtractionResult, ...]
    generated_at: datetime


class BiCompanyIndexEntry(BiContractModel):
    company: BiCompany
    source: BiMaterializationSource | None = None
    current_snapshot_id: SnapshotId | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
