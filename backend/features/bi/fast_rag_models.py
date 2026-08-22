from dataclasses import dataclass

from pydantic import Field

from .models import BiContractModel


class FastRagPipelineSettings(BiContractModel):
    decomposer_model: str = "gpt-5.6-luna"
    decomposer_preset: str = "luna_decomposer"
    embedding_model: str = "text-embedding-3-large"
    retrieval_top_k: int = Field(default=100, gt=0, le=10_000)
    context_cell_limit: int = Field(default=100, gt=0, le=1_000)


class RankedEvidenceCell(BiContractModel):
    cell_id: str = Field(min_length=1, max_length=256)
    sheet_name: str = Field(min_length=1, max_length=128)
    cell_coord: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    source_text: str = Field(min_length=1, max_length=2_000)


@dataclass(frozen=True, slots=True)
class RetrievalIdentity:
    request_id: str
    question: str
    file_name: str
    workbook_hash: str
    index_id: str
