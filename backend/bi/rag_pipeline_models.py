from typing import Literal

from pydantic import Field

from .models import BiContractModel


class RagQueryContext(BiContractModel):
    question_id: str = Field(min_length=1)
    question_text: str = Field(min_length=1)


class RagDocumentContext(BiContractModel):
    file_name: str = Field(min_length=1)
    workbook_hash: str = Field(min_length=1)


class RagSubqueries(BiContractModel):
    query_context: RagQueryContext
    subqueries: tuple[str, ...] = Field(min_length=1)


class RagCellDocument(BiContractModel):
    cell_id: str = Field(min_length=1)
    sheet_name: str = Field(min_length=1)
    cell_coord: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    row_header: tuple[str, ...]
    column_header: tuple[str, ...]
    cell_value: str
    variant: Literal["header_only", "header_with_value"]
    text: str = Field(min_length=1)


class RagDocument(BiContractModel):
    file_name: str = Field(min_length=1)
    workbook_hash: str = Field(min_length=1)
    items: tuple[RagCellDocument, ...] = Field(min_length=1)


class RagIndex(BiContractModel):
    index_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    workbook_hash: str = Field(min_length=1)
    model: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    document_count: int = Field(ge=0)


class RagLoadedIndex(BiContractModel):
    document_output: RagDocument
    index_output: RagIndex


class RagEmbeddings(BiContractModel):
    query_context: RagQueryContext
    items: dict[str, tuple[float, ...]] = Field(min_length=1)


class RagRankedCandidate(BiContractModel):
    rank: int = Field(ge=1)
    cell_id: str = Field(min_length=1)
    score: float
    text: str
    matched_subquery: str


class RagRankedResult(BiContractModel):
    query_context: RagQueryContext
    document_context: RagDocumentContext
    items: tuple[RagRankedCandidate, ...]


class RagFusedCandidate(BiContractModel):
    rank: int = Field(ge=1)
    cell_id: str = Field(min_length=1)
    rrf_score: float = Field(gt=0)
    text: str
    matched_subquery: str


class RagRetrieval(BiContractModel):
    query_context: RagQueryContext
    document_context: RagDocumentContext
    items: tuple[RagFusedCandidate, ...]


class RagContext(BiContractModel):
    query_context: RagQueryContext
    document_context: RagDocumentContext
    top_k_used: int = Field(gt=0)
    adjacent_radius: int = Field(ge=0)
    context_characters: int = Field(ge=0)
    context_blocks: tuple[str, ...] = Field(min_length=1)
    block_count: int = Field(gt=0)


class RagContextOutput(BiContractModel):
    context_json: RagContext
