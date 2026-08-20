import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from ..storage.pgvector_store import PgVectorStore
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .cell_text_embedder import EmbeddedCellTextDocumentDTO
from .embedder import EmbeddingsDTO
from .prebuilt_index_loader import IndexOutputDTO
from .retrieval_models import RankedSearchResultDTO

logger = logging.getLogger(__name__)


class PgVectorRetrieverInputDTO(ModuleInputDTO):
    query_input: EmbeddingsDTO = Field(description="질문 측 서브쿼리 임베딩 입력 포트")
    index_input: IndexOutputDTO = Field(
        description="pgvector Collection Loader 또는 pgvector Index Writer가 생성한 인덱스 참조 DTO"
    )


class PgVectorRetrieverConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=100,
        gt=0,
        le=10000,
        description="각 서브쿼리별 pgvector HNSW 후보 검색 최대 개수",
    )


class PgVectorRetrieverExecutionDTO(PgVectorRetrieverInputDTO, PgVectorRetrieverConfigDTO):
    """Internal union of search inputs and retrieval policy."""


class PgVectorRetrieverModule(ExecutableModule):
    """Executes similarity searches using PostgreSQL pgvector IVFFlat index."""

    definition = ModuleDefinition(
        type="pgvector_retriever",
        label="PostgreSQL pgvector Retriever",
        category="Logic",
        description="질의 임베딩으로 PostgreSQL 16 pgvector DB의 IVFFlat 코사인 인덱스를 실시간 검색합니다.",
        inputs=["query_input", "index_input"],
        outputs=["dense_result"],
        config_fields=["top_k"],
        raw_output=True,
        version="1",
    )
    input_model = PgVectorRetrieverInputDTO
    config_model = PgVectorRetrieverConfigDTO
    execution_model = PgVectorRetrieverExecutionDTO
    output_model = RankedSearchResultDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        """
        Searches selected pgvector collections using the configured query embeddings and ranks the matching documents.
        
        Parameters:
            payload (BaseModel): Execution data containing query embeddings, collection identifiers, retrieval configuration, and document context.
        
        Returns:
            Dict[str, Any]: Query and document context with ranked matches, or an empty item list when no query embeddings are provided.
        
        Raises:
            ModuleExecutionError: If every collection search fails and no matches are available.
        """
        input_data = cast(PgVectorRetrieverExecutionDTO, payload)
        raw_col_name = input_data.index_input.index_id
        target_collections = [c.strip() for c in raw_col_name.split(",") if c.strip()]
        if not target_collections:
            target_collections = [raw_col_name]
        top_k = input_data.top_k
        query_items = list(input_data.query_input.items.items())

        if not query_items:
            return {
                "query_context": input_data.query_input.query_context.model_dump(
                    mode="json"
                ),
                "document_context": {
                    "file_name": input_data.index_input.file_name,
                    "workbook_hash": input_data.index_input.workbook_hash,
                },
                "items": [],
            }

        # Query pgvector across all selected collections for each subquery
        all_hits: List[Tuple[float, Dict[str, Any], str, str]] = []
        failures: List[str] = []
        for target_col in target_collections:
            for query_text, embedding_vector in query_items:
                try:
                    results = self.pgvector_store.similarity_search_by_vector_with_score(
                        collection_name=target_col,
                        embedding=embedding_vector,
                        k=top_k,
                    )
                    for offset, (doc, dist) in enumerate(results):
                        score = 1.0 - float(dist) if dist is not None else 0.5
                        content_str = doc.page_content or ""
                        content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()[:16]
                        doc_id = getattr(doc, "id", None)
                        row_id = doc_id if isinstance(doc_id, str) and doc_id else None
                        persistent_id = (
                            row_id
                            or doc.metadata.get("cell_id")
                            or doc.metadata.get("chunk_id")
                            or doc.metadata.get("id")
                        )
                        cell_id = persistent_id or f"{target_col}:chunk:{content_hash}"
                        raw_doc = {
                            "cell_id": cell_id,
                            "text": doc.page_content,
                            "metadata": doc.metadata,
                        }
                        all_hits.append((score, raw_doc, query_text, target_col))
                except Exception as err:
                    logger.warning(
                        "pgvector 컬렉션 검색 실패: %s (%s)", target_col, err
                    )
                    failures.append(f"{target_col}: {err}")

        if failures and not all_hits:
            raise ModuleExecutionError(
                "PostgreSQL pgvector 유사도 검색 실패: " + "; ".join(failures)
            )

        # Deduplicate and rank by score
        best_by_cell: Dict[Tuple[str, str], Tuple[float, Dict[str, Any], str]] = {}
        for score, raw_doc, query_text, target_col in all_hits:
            dedup_key = (target_col, raw_doc["cell_id"])
            if dedup_key not in best_by_cell or score > best_by_cell[dedup_key][0]:
                best_by_cell[dedup_key] = (score, raw_doc, query_text)

        ranked = sorted(
            best_by_cell.values(),
            key=lambda item: (-item[0], item[1]["cell_id"]),
        )[:top_k]

        return {
            "query_context": input_data.query_input.query_context.model_dump(
                mode="json"
            ),
            "document_context": {
                "file_name": input_data.index_input.file_name,
                "workbook_hash": input_data.index_input.workbook_hash,
            },
            "items": [
                {
                    "rank": rank,
                    "cell_id": doc_info["cell_id"],
                    "score": round(score, 6),
                    "text": doc_info["text"],
                    "matched_subquery": matched_q,
                }
                for rank, (score, doc_info, matched_q) in enumerate(ranked, start=1)
            ],
        }
