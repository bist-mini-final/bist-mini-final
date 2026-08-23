"""Dense retrieval over the exact collection assigned to each subquery."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    BaseModule,
    DocumentContextDTO,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_RETRIEVAL_TOP_K
from modules.embedding.query_embedder import EmbeddingsDTO, RoutedEmbeddingDTO


class RankedSearchCandidateDTO(ModuleDTO):
    rank: int = Field(ge=1)
    index_id: str = Field(min_length=1)
    cell_id: str = Field(min_length=1)
    score: float
    text: str
    matched_subquery: str


class RankedSearchResultDTO(ModuleDTO):
    query_context: QueryContextDTO
    document_context: DocumentContextDTO
    items: List[RankedSearchCandidateDTO]


class PgVectorRetrieverInputDTO(ModuleInputDTO):
    query_input: EmbeddingsDTO


class PgVectorRetrieverConfigDTO(ModuleConfigDTO):
    top_k: int = Field(default=DEFAULT_RETRIEVAL_TOP_K, gt=0, le=10000)


def _document_context(embeddings: EmbeddingsDTO) -> DocumentContextDTO:
    collections = list(
        {
            item.collection.index_id: item.collection
            for item in embeddings.items
        }.values()
    )
    if not collections:
        return DocumentContextDTO(
            file_name="no-routed-document",
            workbook_hash="no-routed-workbook",
        )
    companies = list(
        dict.fromkeys(scope.company_name for scope in collections if scope.company_name)
    )
    sheets = list(
        dict.fromkeys(sheet for scope in collections for sheet in scope.sheet_names)
    )
    return DocumentContextDTO(
        file_name=", ".join(scope.file_name for scope in collections),
        workbook_hash=",".join(scope.workbook_hash for scope in collections),
        index_id=",".join(scope.index_id for scope in collections),
        company_name=companies[0] if len(companies) == 1 else None,
        sheet_names=sheets or None,
    )


class PgVectorRetrieverModule(BaseModule):
    """Runs one bounded HNSW task per routed subquery/collection pair."""

    definition = ModuleDefinition(
        type="pgvector_retriever",
        label="PostgreSQL pgvector Retriever",
        category="Logic",
        description=(
            "Router가 서브쿼리별로 지정한 collection만 HNSW 검색하고 "
            "company/sheet 조건을 SQL에 푸시다운합니다."
        ),
        inputs=["query_input"],
        outputs=["dense_result"],
        config_fields=["top_k"],
        raw_output=True,
        version="3",
    )
    input_model = PgVectorRetrieverInputDTO
    config_model = PgVectorRetrieverConfigDTO
    output_model = RankedSearchResultDTO

    def __init__(self, pgvector_store: PgVectorStore) -> None:
        self.pgvector_store = pgvector_store

    def _search_one(
        self,
        item: RoutedEmbeddingDTO,
        top_k: int,
    ) -> Tuple[int, str, List[Tuple[float, Dict[str, Any]]]]:
        subquery = item.subquery
        query_text = subquery.text or subquery.to_serialized_query()
        company = subquery.company if subquery.company not in ("", "?") else None
        sheets = [subquery.sheet] if subquery.sheet not in ("", "?") else None
        results = self.pgvector_store.similarity_search_by_vector_with_score(
            collection_name=item.collection.index_id,
            embedding=item.vector,
            k=top_k,
            sheet_names=sheets,
            company_name=company,
        )
        if (company or sheets) and not results:
            results = self.pgvector_store.similarity_search_by_vector_with_score(
                collection_name=item.collection.index_id,
                embedding=item.vector,
                k=top_k,
            )
        hits: List[Tuple[float, Dict[str, Any]]] = []
        for document, distance in results:
            text = document.page_content or ""
            metadata = document.metadata or {}
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            persistent_id = (
                metadata.get("cell_id")
                or metadata.get("chunk_id")
                or getattr(document, "id", None)
                or metadata.get("id")
                or f"chunk:{content_hash}"
            )
            hits.append(
                (
                    1.0 - float(distance) if distance is not None else 0.5,
                    {
                        "index_id": item.collection.index_id,
                        "cell_id": str(persistent_id),
                        "text": text,
                        "matched_subquery": query_text,
                    },
                )
            )
        return item.subquery_index, query_text, hits

    def execute(
        self,
        input_data: PgVectorRetrieverInputDTO,
        config: Optional[PgVectorRetrieverConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or PgVectorRetrieverConfigDTO()
        embeddings = input_data.query_input
        if not embeddings.items:
            return {
                "query_context": embeddings.query_context.model_dump(mode="json"),
                "document_context": _document_context(embeddings).model_dump(mode="json"),
                "items": [],
            }

        best_by_subquery: Dict[
            int, Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]]
        ] = {}
        with ThreadPoolExecutor(max_workers=min(8, len(embeddings.items))) as executor:
            results = executor.map(
                lambda item: self._search_one(item, cfg.top_k),
                embeddings.items,
            )
            for subquery_index, _, hits in results:
                best = best_by_subquery.setdefault(subquery_index, {})
                for score, hit in hits:
                    key = (hit["index_id"], hit["cell_id"])
                    if key not in best or score > best[key][0]:
                        best[key] = (score, hit)

        ranked_items: List[Dict[str, Any]] = []
        for subquery_index in sorted(best_by_subquery):
            ranked = sorted(
                best_by_subquery[subquery_index].values(),
                key=lambda value: (-value[0], value[1]["index_id"], value[1]["cell_id"]),
            )[: cfg.top_k]
            ranked_items.extend(
                {
                    "rank": rank,
                    "index_id": hit["index_id"],
                    "cell_id": hit["cell_id"],
                    "score": round(score, 6),
                    "text": hit["text"],
                    "matched_subquery": hit["matched_subquery"],
                }
                for rank, (score, hit) in enumerate(ranked, start=1)
            )
        return {
            "query_context": embeddings.query_context.model_dump(mode="json"),
            "document_context": _document_context(embeddings).model_dump(mode="json"),
            "items": ranked_items,
        }


__all__ = [
    "PgVectorRetrieverConfigDTO",
    "PgVectorRetrieverInputDTO",
    "PgVectorRetrieverModule",
    "RankedSearchCandidateDTO",
    "RankedSearchResultDTO",
]
