"""PostgreSQL pgvector 인덱스에 대해 HNSW 코사인 유사도 검색을 수행하는 고밀도(Dense) 벡터 검색기 모듈.

서브쿼리 임베딩 벡터들과 라우팅 스코프(기업, 시트 필터)를 기반으로
PostgreSQL 데이터베이스의 개별 셀 벡터 테이블을 병렬로 질의하여 상위 Top-K 검색 후보(Ranked Candidates)를 반환합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "query_input": {
        "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
        "items": {"Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?": [0.01, -0.02]}
      },
      "index_input": {
        "index_id": "rag_cells_a1b2c3d4",
        "file_name": "samsung_2023.xlsx",
        "workbook_hash": "a1b2c3d4...",
        "model": "text-embedding-3-large",
        "dimension": 3072,
        "document_count": 1200
      },
      "semantic_match": null
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
      "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "a1b2c3d4..."},
      "items": [
        {
          "rank": 1,
          "cell_id": "IS_C5",
          "score": 0.945,
          "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
          "matched_subquery": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
        }
      ]
    }
    ```
"""

from __future__ import annotations

# ==============================================================================
# 1. Imports
# ==============================================================================
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union

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
from modules.common.config import DEFAULT_MIN_SCOPE_CONFIDENCE, DEFAULT_RETRIEVAL_TOP_K
from modules.embedding.query_embedder import EmbeddingsDTO
from modules.query.llm_query_router import LlmQueryRouterOutputDTO, RouterDecisionDTO
from modules.query.semantic_query_matcher import SemanticQueryMatchOutput
from modules.storage.pgvector_collection_loader import IndexOutputDTO

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
class RankedSearchCandidateDTO(ModuleDTO):
    """Individual cell candidate returned by dense/sparse retrieval."""

    rank: int = Field(ge=1, description="검색기 내부 후보 순위")
    cell_id: str = Field(min_length=1, description="검색된 셀의 고유 ID")
    score: float = Field(description="해당 검색기가 계산한 원본 점수")
    text: str = Field(description="검색된 셀의 직렬화 텍스트")
    matched_subquery: str = Field(description="해당 셀과 매칭된 서브쿼리")


class RankedSearchResultDTO(ModuleDTO):
    """Ranked retrieval output containing matching cell candidates and query context."""

    query_context: QueryContextDTO = Field(
        description="검색 후보가 대응하는 원본 질문 컨텍스트"
    )
    document_context: DocumentContextDTO = Field(
        description="검색 후보가 추출된 원본 문서 컨텍스트"
    )
    items: List[RankedSearchCandidateDTO] = Field(
        description="각 matched_subquery 내부 검색 점수 내림차순 후보 목록"
    )


class PgVectorRetrieverInputDTO(ModuleInputDTO):
    query_input: EmbeddingsDTO = Field(description="질문 측 서브쿼리 임베딩 입력 포트")
    index_input: IndexOutputDTO = Field(
        description="pgvector Collection Loader 또는 pgvector Index Writer가 생성한 인덱스 참조 DTO"
    )
    semantic_match: Optional[
        Union[
            SemanticQueryMatchOutput,
            LlmQueryRouterOutputDTO,
            RouterDecisionDTO,
            Dict[str, Any],
        ]
    ] = Field(
        default=None,
        description="시맨틱 매처 또는 LLM 라우터 결과 (선택, 제공 시 SQL 메타데이터 사전 필터링 적용)",
    )


class PgVectorRetrieverConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        gt=0,
        le=10000,
        description="각 서브쿼리별 pgvector HNSW 후보 검색 최대 개수",
    )
    min_scope_confidence: float = Field(
        default=DEFAULT_MIN_SCOPE_CONFIDENCE,
        ge=0,
        le=1,
        description="시맨틱 스코프 적용을 위한 최소 신뢰도 임계값",
    )


# ==============================================================================
# 3. Helper Functions
# ==============================================================================
def _extract_query_scope(
    query_text: str,
    fallback_company: Optional[str] = None,
    fallback_sheets: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[List[str]]]:
    """Parse canonical Company and Sheet fields with optional routed fallbacks."""
    company = fallback_company
    sheets = fallback_sheets
    if not isinstance(query_text, str):
        return company, sheets

    for part in (value.strip() for value in query_text.split("|")):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key == "company" and normalized_value not in ("", "?"):
            company = normalized_value
        elif normalized_key == "sheet" and normalized_value not in ("", "?"):
            sheets = [normalized_value]
    return company, sheets


extract_query_scope = _extract_query_scope


# ==============================================================================
# 3. Module Implementation
# ==============================================================================
class PgVectorRetrieverModule(BaseModule):
    """Executes similarity searches using PostgreSQL pgvector HNSW index with optional semantic scoping."""

    definition = ModuleDefinition(
        type="pgvector_retriever",
        label="PostgreSQL pgvector Retriever",
        category="Logic",
        description="질의 임베딩으로 PostgreSQL 16 pgvector DB의 HNSW 코사인 인덱스를 실시간 검색하며 시맨틱 스코프가 제공되면 사전 필터링을 수행합니다.",
        inputs=["query_input", "index_input", "semantic_match"],
        outputs=["dense_result"],
        config_fields=["top_k", "min_scope_confidence"],
        raw_output=True,
        version="2",
    )
    input_model = PgVectorRetrieverInputDTO
    config_model = PgVectorRetrieverConfigDTO
    output_model = RankedSearchResultDTO

    def __init__(self, pgvector_store: PgVectorStore) -> None:
        self.pgvector_store = pgvector_store

    def execute(
        self,
        input_data: PgVectorRetrieverInputDTO,
        config: Optional[PgVectorRetrieverConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or PgVectorRetrieverConfigDTO()

        raw_col_name = input_data.index_input.index_id
        target_collections = [c.strip() for c in raw_col_name.split(",") if c.strip()]
        if not target_collections:
            target_collections = [raw_col_name]
        top_k = cfg.top_k
        query_items = list(input_data.query_input.items.items())

        if not query_items:
            return {
                "query_context": input_data.query_input.query_context.model_dump(mode="json"),
                "document_context": {
                    "file_name": input_data.index_input.file_name,
                    "workbook_hash": input_data.index_input.workbook_hash,
                    "index_id": input_data.index_input.index_id,
                },
                "items": [],
            }

        # Resolve semantic scopes if available (from Semantic Matcher or LLM Router)
        match_raw = input_data.semantic_match
        match: Any = getattr(match_raw, "semantic_match", match_raw)
        global_sheets: List[str] = []
        global_company: Optional[str] = None
        if match and match.matched and match.confidence >= cfg.min_scope_confidence:
            if match.sheets:
                global_sheets = list(match.sheets)
            if match.company_name:
                global_company = match.company_name

        def _search_one(
            task: Tuple[str, List[float], str],
        ) -> Tuple[str, str, List[Tuple[float, Dict[str, Any]]]]:
            query_text, embedding_vector, target_col = task
            sq_company, sq_sheets = extract_query_scope(
                query_text,
                fallback_company=global_company,
                fallback_sheets=global_sheets,
            )
            results = self.pgvector_store.similarity_search_by_vector_with_score(
                collection_name=target_col,
                embedding=embedding_vector,
                k=top_k,
                sheet_names=sq_sheets or None,
                company_name=sq_company or None,
            )
            if (sq_sheets or sq_company) and not results:
                results = self.pgvector_store.similarity_search_by_vector_with_score(
                    collection_name=target_col,
                    embedding=embedding_vector,
                    k=top_k,
                )
            hits: List[Tuple[float, Dict[str, Any]]] = []
            for doc, dist in results:
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
                hits.append(
                    (
                        score,
                        {
                            "cell_id": persistent_id
                            or f"{target_col}:chunk:{content_hash}",
                            "text": doc.page_content,
                            "metadata": doc.metadata,
                        },
                    )
                )
            return query_text, target_col, hits

        tasks = [
            (query_text, embedding_vector, target_col)
            for query_text, embedding_vector in query_items
            for target_col in target_collections
        ]
        best_by_query_cell: Dict[
            str, Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]]
        ] = {query_text: {} for query_text, _ in query_items}
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
            for query_text, target_col, hits in executor.map(_search_one, tasks):
                query_best = best_by_query_cell[query_text]
                for score, raw_doc in hits:
                    dedup_key = (target_col, raw_doc["cell_id"])
                    if dedup_key not in query_best or score > query_best[dedup_key][0]:
                        query_best[dedup_key] = (score, raw_doc)

        ranked_items: List[Dict[str, Any]] = []
        for query_text, _ in query_items:
            ranked = sorted(
                best_by_query_cell[query_text].values(),
                key=lambda item: (-item[0], item[1]["cell_id"]),
            )[:top_k]
            ranked_items.extend(
                {
                    "rank": rank,
                    "cell_id": doc_info["cell_id"],
                    "score": round(score, 6),
                    "text": doc_info["text"],
                    "matched_subquery": query_text,
                }
                for rank, (score, doc_info) in enumerate(ranked, start=1)
            )

        return {
            "query_context": input_data.query_input.query_context.model_dump(mode="json"),
            "document_context": {
                "file_name": input_data.index_input.file_name,
                "workbook_hash": input_data.index_input.workbook_hash,
                "index_id": input_data.index_input.index_id,
            },
            "items": ranked_items,
        }


# ==============================================================================
# 4. Exports
# ==============================================================================
__all__ = [
    "PgVectorRetrieverConfigDTO",
    "PgVectorRetrieverInputDTO",
    "PgVectorRetrieverModule",
    "RankedSearchCandidateDTO",
    "RankedSearchResultDTO",
    "extract_query_scope",
]
