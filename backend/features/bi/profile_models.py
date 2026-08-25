from datetime import date

from pydantic import Field

from .models import (
    IDENTIFIER_PATTERN,
    AmountScale,
    BiContractModel,
    BiMaterializationSource,
    PeriodKind,
)


class BiProfileRetrievalRequest(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    source: BiMaterializationSource
    question: str = Field(min_length=1, max_length=1_000)
    sheet_name: str | None = Field(default=None, min_length=1, max_length=128)


class BiPeriodReaderPayload(BiContractModel):
    """LLM 응답 전용 period DTO.

    `period_id`는 서버의 `_canonical_period()`에서 결정론적으로 생성하므로
    LLM에게 엄격한 regex 패턴을 요구하지 않는다.
    """

    kind: PeriodKind
    label: str = Field(min_length=1, max_length=64)
    source_label: str = Field(min_length=1, max_length=64)
    end_date: date | None
    ordinal: int


class BiProfilePeriodReaderResponse(BiContractModel):
    period: BiPeriodReaderPayload
    evidence_cell_ids: tuple[str, ...] = ()


class BiPeriodDiscoveryReaderResponse(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    periods: tuple[BiProfilePeriodReaderResponse, ...] = Field(min_length=1)


class BiUnitDiscoveryReaderResponse(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    scale: AmountScale | None = None
    evidence_cell_ids: tuple[str, ...] = ()
