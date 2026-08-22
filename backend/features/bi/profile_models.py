from pydantic import Field

from .models import (
    IDENTIFIER_PATTERN,
    AmountScale,
    BiContractModel,
    BiMaterializationSource,
    BiPeriod,
)


class BiProfileRetrievalRequest(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    source: BiMaterializationSource
    question: str = Field(min_length=1, max_length=1_000)
    sheet_name: str | None = Field(default=None, min_length=1, max_length=128)


class BiProfilePeriodReaderResponse(BiContractModel):
    period: BiPeriod
    evidence_cell_ids: tuple[str, ...] = ()


class BiDocumentProfileReaderResponse(BiContractModel):
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    periods: tuple[BiProfilePeriodReaderResponse, ...] = Field(min_length=1)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    scale: AmountScale | None = None
    evidence_cell_ids: tuple[str, ...] = ()
