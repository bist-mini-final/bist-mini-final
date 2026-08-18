from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from ..storage.vector_index import VectorIndexStore
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .cell_text_embedder import EmbeddedCellTextDocumentDTO
from .embedder import EmbeddingsDTO
from .retrieval_models import RankedSearchResultDTO
from .vector_index_writer import VectorIndexDTO


class DenseRetrieverInputDTO(ModuleInputDTO):
    query_input: EmbeddingsDTO = Field(description="질문 측 서브쿼리 임베딩 입력 포트")
    index_input: VectorIndexDTO = Field(
        description="Vector Index Writer가 생성한 영속 문서 인덱스 입력 포트"
    )


class DenseRetrieverConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=1000,
        gt=0,
        le=10000,
        description="각 서브쿼리별 Dense 후보 최대 개수",
    )


class DenseRetrieverExecutionDTO(DenseRetrieverInputDTO, DenseRetrieverConfigDTO):
    """Internal union of search inputs and retrieval policy."""


class DenseRetrieverModule(ExecutableModule):
    definition = ModuleDefinition(
        type="dense_retriever",
        label="Dense Vector Retriever",
        category="Logic",
        description="질의 임베딩으로 영속 문서 벡터 인덱스를 검색합니다.",
        inputs=["query_input", "index_input"],
        outputs=["dense_result"],
        config_fields=["top_k"],
        raw_output=True,
        version="7",
    )
    input_model = DenseRetrieverInputDTO
    config_model = DenseRetrieverConfigDTO
    execution_model = DenseRetrieverExecutionDTO
    output_model = RankedSearchResultDTO

    def __init__(self, index_store: Optional[VectorIndexStore] = None) -> None:
        self.index_store = index_store or VectorIndexStore()

    @staticmethod
    def _rank_query(
        hits: List[Tuple[float, Dict[str, Any]]],
        query: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        best_by_cell: Dict[str, Tuple[float, EmbeddedCellTextDocumentDTO, str]] = {}
        for score, raw_document in hits:
            document = EmbeddedCellTextDocumentDTO.model_validate(raw_document)
            current = best_by_cell.get(document.cell_id)
            if current is None or score > current[0]:
                best_by_cell[document.cell_id] = (score, document, query)
        ranked = sorted(
            best_by_cell.values(),
            key=lambda item: (-item[0], item[1].cell_id),
        )[:top_k]
        return [
            {
                "rank": rank,
                "cell_id": document.cell_id,
                "score": round(score, 10),
                "text": document.text,
                "matched_subquery": matched_query,
            }
            for rank, (score, document, matched_query) in enumerate(ranked, start=1)
        ]

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(DenseRetrieverExecutionDTO, payload)
        metadata = self.index_store.metadata(input_data.index_input.index_id)
        expected_metadata = {
            "file_name": input_data.index_input.file_name,
            "workbook_hash": input_data.index_input.workbook_hash,
            "model": input_data.index_input.model,
            "dimension": input_data.index_input.dimension,
            "document_count": input_data.index_input.document_count,
        }
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise ModuleExecutionError(
                "벡터 인덱스 참조 DTO와 저장된 인덱스 메타데이터가 일치하지 않습니다"
            )
        query_items = list(input_data.query_input.items.items())
        ranked_items: List[Dict[str, Any]] = []
        for query, query_vector in query_items:
            hits = self.index_store.search(
                input_data.index_input.index_id,
                query_vector,
                min(
                    input_data.index_input.document_count,
                    input_data.top_k * 2,
                ),
            )
            ranked_items.extend(
                self._rank_query(
                    hits,
                    query,
                    input_data.top_k,
                )
            )

        return {
            "query_context": input_data.query_input.query_context.model_dump(
                mode="json"
            ),
            "document_context": {
                "file_name": input_data.index_input.file_name,
                "workbook_hash": input_data.index_input.workbook_hash,
            },
            "items": ranked_items,
        }
