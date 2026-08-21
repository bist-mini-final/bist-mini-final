"""pgvector retriever that applies a semantic sheet scope only when it is safe."""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from ..storage.pgvector_store import PgVectorStore
from .base import ExecutableModule, ModuleConfigDTO, ModuleDefinition, ModuleExecutionError, ModuleInputDTO
from .embedder import EmbeddingsDTO
from .prebuilt_index_loader import IndexOutputDTO
from .retrieval_models import RankedSearchResultDTO
from .semantic_query_matcher import SemanticQueryMatchOutput


logger = logging.getLogger(__name__)


class SemanticScopedPgVectorRetrieverInput(ModuleInputDTO):
    query_input: EmbeddingsDTO
    index_input: IndexOutputDTO
    semantic_match: SemanticQueryMatchOutput


class SemanticScopedPgVectorRetrieverConfig(ModuleConfigDTO):
    top_k: int = Field(default=1000, gt=0, le=10000)
    min_scope_confidence: float = Field(default=0.80, ge=0, le=1)


class SemanticScopedPgVectorRetrieverExecution(
    SemanticScopedPgVectorRetrieverInput, SemanticScopedPgVectorRetrieverConfig
):
    """Runtime union of pgvector retrieval inputs and scope policy."""


class SemanticScopedPgVectorRetrieverModule(ExecutableModule):
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

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(SemanticScopedPgVectorRetrieverExecution, payload)
        collections = [item.strip() for item in input_data.index_input.index_id.split(",") if item.strip()]
        if not collections:
            raise ModuleExecutionError("pgvector 컬렉션 참조가 비어 있습니다")

        match = input_data.semantic_match
        allowed_sheets = list(match.sheets) if (
            match.matched
            and match.confidence >= input_data.min_scope_confidence
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
                        k=input_data.top_k,
                        sheet_names=allowed_sheets or None,
                    )
                    if allowed_sheets and not results:
                        results = self.pgvector_store.similarity_search_by_vector_with_score(
                            collection_name=collection,
                            embedding=vector,
                            k=input_data.top_k,
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
        ranked = sorted(best.values(), key=lambda item: (-item[0], item[1]["cell_id"]))[:input_data.top_k]
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
