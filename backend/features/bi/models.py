from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Final, Literal, NewType

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

IDENTIFIER_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
WORKBOOK_HASH_PATTERN: Final = r"^[a-f0-9]{64}$"

CompanyId = NewType("CompanyId", str)
SnapshotId = NewType("SnapshotId", str)
JobId = NewType("JobId", str)
PeriodId = NewType("PeriodId", str)
IndexId = NewType("IndexId", str)


@unique
class MetricId(StrEnum):
    REVENUE = "revenue"
    REVENUE_YOY_GROWTH = "revenue_yoy_growth"
    OPERATING_INCOME = "operating_income"
    OPERATING_MARGIN = "operating_margin"
    NET_INCOME = "net_income"
    NET_MARGIN = "net_margin"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPITAL_EXPENDITURE = "capital_expenditure"
    FREE_CASH_FLOW = "free_cash_flow"
    FREE_CASH_FLOW_MARGIN = "free_cash_flow_margin"
    CASH_AND_SHORT_TERM_INVESTMENTS = "cash_and_short_term_investments"
    SHORT_TERM_DEBT = "short_term_debt"
    CURRENT_PORTION_OF_LONG_TERM_DEBT = "current_portion_of_long_term_debt"
    LONG_TERM_DEBT = "long_term_debt"
    TOTAL_DEBT = "total_debt"
    NET_DEBT = "net_debt"
    TOTAL_ASSETS = "total_assets"
    TOTAL_LIABILITIES = "total_liabilities"
    TOTAL_EQUITY = "total_equity"
    DEBT_RATIO = "debt_ratio"
    NET_DEBT_RATIO = "net_debt_ratio"


@unique
class MetricStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    NOT_MEANINGFUL = "not_meaningful"


@unique
class SnapshotStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"


@unique
class RefreshStatus(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    INDEXING = "indexing"
    PROFILING = "profiling"
    EXTRACTING = "extracting"
    MATERIALIZING = "materializing"
    FAILED = "failed"


@unique
class MaterializationStatus(StrEnum):
    QUEUED = "queued"
    INDEXING = "indexing"
    PROFILING = "profiling"
    EXTRACTING = "extracting"
    MATERIALIZING = "materializing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


@unique
class PeriodKind(StrEnum):
    FY = "fy"
    LTM = "ltm"


@unique
class ValueKind(StrEnum):
    AMOUNT = "amount"
    PERCENT = "percent"


@unique
class AmountScale(StrEnum):
    ONES = "ones"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"


class BiContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class BiCompany(BiContractModel):
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)


class BiMaterializationSource(BiContractModel):
    file_name: str = Field(min_length=1, max_length=255)
    workbook_hash: str = Field(pattern=WORKBOOK_HASH_PATTERN)
    index_id: IndexId = Field(pattern=IDENTIFIER_PATTERN)

    @field_validator("file_name")
    @classmethod
    def require_server_owned_file_name(cls, value: str) -> str:
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise PydanticCustomError(
                "file_name_only",
                "file_name must not contain a file system path",
            )
        return value


class BiSnapshotMeta(BiContractModel):
    snapshot_id: SnapshotId = Field(pattern=IDENTIFIER_PATTERN)
    workbook_hash: str = Field(pattern=WORKBOOK_HASH_PATTERN)
    status: SnapshotStatus
    generated_at: datetime
    catalog_version: str = Field(min_length=1, max_length=32)
    formula_version: str = Field(min_length=1, max_length=32)


class BiRefreshState(BiContractModel):
    status: RefreshStatus
    job_id: JobId | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    started_at: datetime | None = None
    message: str | None = Field(default=None, max_length=500)


class BiPeriod(BiContractModel):
    period_id: PeriodId = Field(pattern=IDENTIFIER_PATTERN)
    kind: PeriodKind
    label: str = Field(min_length=1, max_length=64)
    source_label: str = Field(min_length=1, max_length=64)
    end_date: date | None
    ordinal: int


class BiEvidence(BiContractModel):
    cell_id: str = Field(min_length=1, max_length=256)
    sheet_name: str = Field(min_length=1, max_length=128)
    cell_coord: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    source_text: str = Field(min_length=1, max_length=2_000)


class AvailableObservation(BiContractModel):
    period_id: PeriodId = Field(pattern=IDENTIFIER_PATTERN)
    status: Literal[MetricStatus.AVAILABLE]
    raw_value: str | None = Field(default=None, min_length=1, max_length=256)
    normalized_value: Decimal
    evidence: tuple[BiEvidence, ...] = ()
    notes: tuple[str, ...] = ()


class UnavailableObservation(BiContractModel):
    period_id: PeriodId = Field(pattern=IDENTIFIER_PATTERN)
    status: Literal[
        MetricStatus.MISSING,
        MetricStatus.AMBIGUOUS,
        MetricStatus.INVALID,
        MetricStatus.NOT_MEANINGFUL,
    ]
    raw_value: str | None = Field(default=None, max_length=256)
    normalized_value: None = None
    evidence: tuple[BiEvidence, ...] = ()
    notes: tuple[str, ...] = ()
    reason: str = Field(min_length=1, max_length=500)


MetricObservation = Annotated[
    AvailableObservation | UnavailableObservation,
    Field(discriminator="status"),
]


class MetricSeries(BiContractModel):
    metric_id: MetricId
    label: str = Field(min_length=1, max_length=100)
    value_kind: ValueKind
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    scale: AmountScale | None = None
    status: MetricStatus
    observations: tuple[MetricObservation, ...]


class BiIssue(BiContractModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9._-]{0,127}$")
    message: str = Field(min_length=1, max_length=500)
    metric_id: MetricId | None = None


class BiDashboardSnapshot(BiContractModel):
    schema_version: Literal[1]
    company: BiCompany
    source: BiMaterializationSource
    snapshot: BiSnapshotMeta
    refresh: BiRefreshState
    periods: tuple[BiPeriod, ...]
    metrics: dict[MetricId, MetricSeries]
    issues: tuple[BiIssue, ...]


class BiMaterializationRequest(BiContractModel):
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    source: BiMaterializationSource


class BiMaterializationJob(BiContractModel):
    job_id: JobId = Field(pattern=IDENTIFIER_PATTERN)
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    workbook_hash: str = Field(pattern=WORKBOOK_HASH_PATTERN)
    status: MaterializationStatus
    completed_requests: int = Field(ge=0)
    total_requests: int = Field(ge=0)
    published_snapshot_id: SnapshotId | None = Field(
        default=None,
        pattern=IDENTIFIER_PATTERN,
    )
    error_code: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9._-]{0,127}$",
    )
    message: str | None = Field(default=None, max_length=500)
    started_at: datetime
    updated_at: datetime
