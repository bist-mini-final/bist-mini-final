from __future__ import annotations

import hashlib
import logging
from typing import Optional, Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from modules.common.config import DEFAULT_MIN_SCOPE_CONFIDENCE
from modules.embedding.embedder import EmbeddingsDTO
from modules.query.semantic_query_matcher import SemanticQueryMatchOutput
from modules.retrieval.retrieval_models import RankedSearchCandidateDTO, RankedSearchResultDTO
from modules.storage.pgvector_collection_loader import IndexOutputDTO

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


class PgVectorRetrieverModule(BaseModule):
    """Executes similarity searches using PostgreSQL pgvector HNSW index."""

    definition = ModuleDefinition(
        type="pgvector_retriever",
        label="PostgreSQL pgvector Retriever",
        category="Logic",
        description="질의 임베딩으로 PostgreSQL 16 pgvector DB의 HNSW 코사인 인덱스를 실시간 검색합니다.",
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

    def execute(
        self,
        input_data: PgVectorRetrieverInputDTO,
        config: Optional[PgVectorRetrieverConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Searches selected pgvector collections using the configured query embeddings and ranks the matching documents.
        """
        if config is None and isinstance(input_data, PgVectorRetrieverExecutionDTO):
            cfg = input_data
        else:
            cfg = config or PgVectorRetrieverConfigDTO()
        raw_col_name = input_data.index_input.index_id
        target_collections = [c.strip() for c in raw_col_name.split(",") if c.strip()]
        if not target_collections:
            target_collections = [raw_col_name]
        top_k = cfg.top_k
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

        # Query pgvector across all selected collections for each subquery in parallel
        from concurrent.futures import ThreadPoolExecutor

        all_hits: List[Tuple[float, Dict[str, Any], str, str]] = []
        failures: List[str] = []

        tasks = [
            (target_col, query_text, embedding_vector)
            for target_col in target_collections
            for query_text, embedding_vector in query_items
        ]

        def _search_single_subquery(
            task: Tuple[str, str, Any]
        ) -> Tuple[str, str, List[Any], Optional[Exception]]:
            """
            Search one collection for a subquery embedding.
            
            Parameters:
            	task (Tuple[str, str, Any]): Collection name, subquery text, and query embedding.
            
            Returns:
            	Tuple[str, str, List[Any], Optional[Exception]]: The collection name, subquery text, search results, and any exception raised during the search.
            """
            col, q_text, q_vec = task
            try:
                res = self.pgvector_store.similarity_search_by_vector_with_score(
                    collection_name=col,
                    embedding=q_vec,
                    k=top_k,
                )
                return col, q_text, res, None
            except Exception as err:
                return col, q_text, [], err

        max_workers = min(5, max(1, len(tasks)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_results = list(executor.map(_search_single_subquery, tasks))

        for target_col, query_text, results, err in future_results:
            if err is not None:
                logger.warning(
                    "pgvector 컬렉션 검색 실패: %s (%s)", target_col, err
                )
                failures.append(f"{target_col}: {err}")
                continue

            for offset, (doc, dist) in enumerate(results):
                score = 1.0 - float(dist) if dist is not None else 0.5
                content_str = doc.page_content or ""
                content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()[:16]
                doc_id = getattr(doc, "id", None)
                row_id = doc_id if isinstance(doc_id, str) and doc_id else None
                persistent_id = (
                    doc.metadata.get("cell_id")
                    or doc.metadata.get("chunk_id")
                    or row_id
                    or doc.metadata.get("id")
                )
                cell_id = persistent_id or f"{target_col}:chunk:{content_hash}"
                raw_doc = {
                    "cell_id": cell_id,
                    "text": doc.page_content,
                    "metadata": doc.metadata,
                }
                all_hits.append((score, raw_doc, query_text, target_col))

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


# ==============================================================================
# 2. Semantic Scoped PgVector Retriever Module
# ==============================================================================

class SemanticScopedPgVectorRetrieverInput(ModuleInputDTO):
    query_input: EmbeddingsDTO
    index_input: IndexOutputDTO
    semantic_match: SemanticQueryMatchOutput




class SemanticScopedPgVectorRetrieverConfig(ModuleConfigDTO):
    top_k: int = Field(default=1000, gt=0, le=10000)
    min_scope_confidence: float = Field(default=DEFAULT_MIN_SCOPE_CONFIDENCE, ge=0, le=1)


class SemanticScopedPgVectorRetrieverExecution(
    SemanticScopedPgVectorRetrieverInput, SemanticScopedPgVectorRetrieverConfig
):
    """Runtime union of pgvector retrieval inputs and scope policy."""


class SemanticScopedPgVectorRetrieverModule(BaseModule):
    """Use SQL sheet filtering only for structured, confident semantic plans."""

    definition = ModuleDefinition(
        type="semantic_scoped_pgvector_retriever",
        label="Semantic-Scoped pgvector Retriever",
        category="Logic",
        description="정답셋 기반 분해 계획과 충분한 신뢰도가 있을 때만 pgvector를 시트 범위로 검색하고, 결과가 없거나 불확실하면 전체 컬렉션을 검색합니다.",
        inputs=["query_input", "index_input", "semantic_match"],
        outputs=["dense_result"],
        config_fields=["top_k", "min_scope_confidence"],
        raw_output=True,
        version="1",
    )
    input_model = SemanticScopedPgVectorRetrieverInput
    config_model = SemanticScopedPgVectorRetrieverConfig
    execution_model = SemanticScopedPgVectorRetrieverExecution
    output_model = RankedSearchResultDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()

    @staticmethod
    def _candidate(
        collection: str, query: str, doc: Any, distance: float
    ) -> Tuple[float, Dict[str, Any], str, str]:
        text = doc.page_content or ""
        metadata = doc.metadata or {}
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        document_id = getattr(doc, "id", None)
        persistent_id = (
            document_id if isinstance(document_id, str) and document_id else None
        ) or metadata.get("cell_id") or metadata.get("chunk_id") or metadata.get("id")
        return (
            1.0 - float(distance) if distance is not None else 0.5,
            {
                "cell_id": persistent_id or f"{collection}:chunk:{content_hash}",
                "text": text,
            },
            query,
            collection,
        )

    def execute(
        self,
        input_data: SemanticScopedPgVectorRetrieverInput,
        config: Optional[SemanticScopedPgVectorRetrieverConfig] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, SemanticScopedPgVectorRetrieverExecution):
            cfg = input_data
        else:
            cfg = config or SemanticScopedPgVectorRetrieverConfig()
        collections = [item.strip() for item in input_data.index_input.index_id.split(",") if item.strip()]
        if not collections:
            raise ModuleExecutionError("pgvector 컬렉션 참조가 비어 있습니다")

        match = input_data.semantic_match
        allowed_sheets = list(match.sheets) if (
            match.matched
            and match.confidence >= cfg.min_scope_confidence
            and match.subqueries
            and match.sheets
        ) else []

        all_hits: List[Tuple[float, Dict[str, Any], str, str]] = []
        failures: List[str] = []
        for collection in collections:
            for query, vector in input_data.query_input.items.items():
                try:
                    # A scoped query that finds nothing must not turn a correct
                    # semantic plan into an empty answer. Fall back per query.
                    results = self.pgvector_store.similarity_search_by_vector_with_score(
                        collection_name=collection,
                        embedding=vector,
                        k=cfg.top_k,
                        sheet_names=allowed_sheets or None,
                    )
                    if allowed_sheets and not results:
                        results = self.pgvector_store.similarity_search_by_vector_with_score(
                            collection_name=collection,
                            embedding=vector,
                            k=cfg.top_k,
                        )
                    all_hits.extend(
                        self._candidate(collection, query, doc, distance)
                        for doc, distance in results
                    )
                except Exception as error:
                    logger.warning("pgvector 컬렉션 검색 실패: %s (%s)", collection, error)
                    failures.append(f"{collection}: {error}")

        if failures and not all_hits:
            raise ModuleExecutionError("PostgreSQL pgvector 유사도 검색 실패: " + "; ".join(failures))

        best: Dict[Tuple[str, str], Tuple[float, Dict[str, Any], str]] = {}
        for score, doc, query, collection in all_hits:
            key = (collection, doc["cell_id"])
            if key not in best or score > best[key][0]:
                best[key] = (score, doc, query)
        ranked = sorted(best.values(), key=lambda item: (-item[0], item[1]["cell_id"]))[:cfg.top_k]
        return {
            "query_context": input_data.query_input.query_context.model_dump(mode="json"),
            "document_context": {
                "file_name": input_data.index_input.file_name,
                "workbook_hash": input_data.index_input.workbook_hash,
            },
            "items": [
                {
                    "rank": rank,
                    "cell_id": doc["cell_id"],
                    "score": round(score, 6),
                    "text": doc["text"],
                    "matched_subquery": query,
                }
                for rank, (score, doc, query) in enumerate(ranked, start=1)
            ],
        }

__all__ = [
    "PgVectorRetrieverConfigDTO",
    "PgVectorRetrieverExecutionDTO",
    "PgVectorRetrieverInputDTO",
    "PgVectorRetrieverModule",
    "SemanticScopedPgVectorRetrieverConfig",
    "SemanticScopedPgVectorRetrieverExecution",
    "SemanticScopedPgVectorRetrieverInput",
    "SemanticScopedPgVectorRetrieverModule",
]
