"""Dense retrieval variant that consumes the semantic matcher's sheet scope."""

import re
from typing import Any, Dict, List, cast

from pydantic import BaseModel, Field

from ..vector_index_store import VectorIndexStore
from .base import ExecutableModule, ModuleDefinition, ModuleDTO, ModuleExecutionError
from .dense_retriever import DenseRetrieverModule
from .embedder import EmbeddingsDTO
from .retrieval_models import RankedSearchResultDTO
from .semantic_query_matcher import SemanticQueryMatchOutput
from .vector_index_writer import VectorIndexDTO


def _normalized_sheet_name(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", value.lower())


class SemanticScopedDenseRetrieverInput(ModuleDTO):
    query_input: EmbeddingsDTO
    index_input: VectorIndexDTO
    semantic_match: SemanticQueryMatchOutput
    top_k: int = Field(default=1000, gt=0, le=10000)


class SemanticScopedDenseRetrieverModule(ExecutableModule):
    definition = ModuleDefinition(
        type="semantic_scoped_dense_retriever",
        label="Semantic-Scoped Dense Retriever",
        category="Logic",
        description="시맨틱 매칭된 시트 안에서만 Dense 검색하고, 매칭이 불확실하면 기존처럼 전체 인덱스를 검색합니다.",
        inputs=["query_input", "index_input", "semantic_match"],
        outputs=["dense_result"],
        config_fields=["top_k"],
        raw_output=True,
        version="1",
    )
    input_model = SemanticScopedDenseRetrieverInput
    output_model = RankedSearchResultDTO

    def __init__(self, index_store: VectorIndexStore | None = None) -> None:
        self.index_store = index_store or VectorIndexStore()

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(SemanticScopedDenseRetrieverInput, payload)
        metadata = self.index_store.metadata(input_data.index_input.index_id)
        expected = {
            "workbook_hash": input_data.index_input.workbook_hash,
            "model": input_data.index_input.model,
            "dimension": input_data.index_input.dimension,
            "document_count": input_data.index_input.document_count,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ModuleExecutionError("Vector index metadata does not match the supplied index reference")

        match = input_data.semantic_match
        allowed_sheets = {
            _normalized_sheet_name(sheet) for sheet in match.sheets
        } if match.matched and match.sheets else set()
        # Searching the full flat index before applying a scope is deliberate:
        # a scope can have fewer documents than top_k, and an empty/renamed sheet
        # must never turn a confident route into an empty retrieval result.
        limit = input_data.index_input.document_count if allowed_sheets else min(
            input_data.index_input.document_count, input_data.top_k * 2
        )
        ranked_items: List[Dict[str, Any]] = []
        for query, vector in input_data.query_input.items.items():
            hits = self.index_store.search(input_data.index_input.index_id, vector, limit)
            if allowed_sheets:
                scoped_hits = [
                    hit for hit in hits
                    if _normalized_sheet_name(str(hit[1].get("sheet_name", ""))) in allowed_sheets
                ]
                if scoped_hits:
                    hits = scoped_hits
            ranked_items.extend(DenseRetrieverModule._rank_query(hits, query, input_data.top_k))
        return {"question_id": input_data.query_input.question_id.upper(), "items": ranked_items}
