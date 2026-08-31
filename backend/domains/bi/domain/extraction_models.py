from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from .models import (
    IDENTIFIER_PATTERN,
    WORKBOOK_HASH_PATTERN,
    AmountScale,
    BiContractModel,
    BiMaterializationSource,
    MetricId,
    MetricObservation,
    MetricStatus,
    PeriodId,
    ValueKind,
)


class BiMetricExtractionRequest(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    metric_id: MetricId
    period_id: PeriodId = Field(pattern=IDENTIFIER_PATTERN)
    period_label: str = Field(min_length=1, max_length=64)
    source: BiMaterializationSource


class BiRetrievalRequest(BiContractModel):
    extraction: BiMetricExtractionRequest
    question: str = Field(min_length=1, max_length=1_000)


class BiContextCell(BiContractModel):
    cell_id: str = Field(min_length=1, max_length=256)
    sheet_name: str = Field(min_length=1, max_length=128)
    cell_coord: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    source_text: str = Field(min_length=1, max_length=2_000)


class BiRetrievedContext(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    file_name: str = Field(min_length=1, max_length=255)
    workbook_hash: str = Field(pattern=WORKBOOK_HASH_PATTERN)
    index_id: str = Field(pattern=IDENTIFIER_PATTERN)
    context_blocks: tuple[str, ...] = Field(min_length=1)
    cells: tuple[BiContextCell, ...] = Field(min_length=1)


class BiMetricReaderResponse(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    metric_id: MetricId
    period_id: PeriodId = Field(pattern=IDENTIFIER_PATTERN)
    status: MetricStatus
    raw_value: str | None
    normalized_value: Decimal | None
    currency: Annotated[str | None, Field(pattern=r"^[A-Z]{3}$")]
    scale: AmountScale | None
    evidence_cell_ids: tuple[str, ...]
    notes: tuple[str, ...]
    reason: str | None


@dataclass(frozen=True, slots=True)
class ReaderContractFailure:
    code: str


@dataclass(frozen=True, slots=True)
class BiMetricExtractionStatusError(RuntimeError):
    status: MetricStatus

    def __str__(self) -> str:
        return f"metric extraction status is unavailable: {self.status}"


MetricReaderResult = BiMetricReaderResponse | ReaderContractFailure


class BiMetricExtractionResult(BiContractModel):
    metric_id: MetricId
    period_id: PeriodId = Field(pattern=IDENTIFIER_PATTERN)
    value_kind: ValueKind
    currency: Annotated[str | None, Field(pattern=r"^[A-Z]{3}$")]
    scale: AmountScale | None
    observation: MetricObservation

