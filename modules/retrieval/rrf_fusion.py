from __future__ import annotations

# ==============================================================================
# 1. Imports
# ==============================================================================
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from modules.common.base_module import (
    BaseModule,
    DocumentContextDTO,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import (
    DEFAULT_RETRIEVAL_TOP_K,
    DEFAULT_RRF_K,
)
from modules.retrieval.pgvector_retriever import (
    RankedSearchCandidateDTO,
    RankedSearchResultDTO,
)

logger = logging.getLogger(__name__)

CandidateKey = Tuple[str, str]


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
class RrfCandidateDTO(ModuleDTO):
    """Single cell candidate after Reciprocal Rank Fusion."""

    rank: int = Field(ge=1, description="RRF 결합 순위")
    cell_id: str = Field(min_length=1, description="검색된 셀의 고유 ID")
    rrf_score: float = Field(gt=0, description="Reciprocal Rank Fusion 점수")
    text: str = Field(description="검색된 셀의 직렬화 텍스트")
    matched_subquery: str = Field(description="해당 셀과 매칭된 서브쿼리")


class RetrievalDTO(ModuleDTO):
    """Fused retrieval result containing top cell candidates and contexts."""

    query_context: QueryContextDTO = Field(
        description="결합 검색 결과가 대응하는 원본 질문 컨텍스트"
    )
    document_context: DocumentContextDTO = Field(
        description="결합 검색 결과가 참조하는 원본 문서 컨텍스트"
    )
    items: List[RrfCandidateDTO] = Field(description="RRF 점수 내림차순 결합 후보")
class RrfFusionInputDTO(ModuleInputDTO):
    bm25_result: RankedSearchResultDTO = Field(description="BM25/Sparse 서브쿼리별 후보 순위")
    dense_result: RankedSearchResultDTO = Field(description="Dense 서브쿼리별 후보 순위")


class RrfFusionConfigDTO(ModuleConfigDTO):
    rrf_k: int = Field(
        default=DEFAULT_RRF_K,
        ge=1,
        le=1000,
        description="RRF 순위 완화 상수 (기본값: 60)",
    )
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        gt=0,
        le=1000,
        description="결합 후 유지할 최대 셀 후보 개수",
    )
    bm25_weight: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Sparse 키워드 검색 가중치",
    )
    dense_weight: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Dense 벡터 검색 가중치",
    )


RrfFusionExecutionDTO = RrfFusionInputDTO


# ==============================================================================
# 3. Module Implementation
# ==============================================================================
class RrfFusionModule(BaseModule):
    definition = ModuleDefinition(
        type="rrf_fusion",
        label="RRF Fusion",
        category="Logic",
        description="서브쿼리별 Sparse(BM25/GIN) 및 Dense(pgvector) 검색 순위를 상호 순위 융합(RRF)하여 최적 셀 후보를 선별합니다.",
        inputs=["bm25_result", "dense_result"],
        outputs=["retrieval_json"],
        config_fields=["rrf_k", "top_k", "bm25_weight", "dense_weight"],
        raw_output=True,
        version="4",
    )
    input_model = RrfFusionInputDTO
    config_model = RrfFusionConfigDTO
    output_model = RetrievalDTO

    def execute(
        self,
        input_data: RrfFusionInputDTO,
        config: Optional[RrfFusionConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or RrfFusionConfigDTO()

        bm25_query = input_data.bm25_result.query_context
        dense_query = input_data.dense_result.query_context
        if bm25_query.question_id != dense_query.question_id:
            raise ModuleExecutionError(
                "BM25와 Dense 결과의 question_id가 일치하지 않습니다"
            )

        bm25_document = input_data.bm25_result.document_context
        dense_document = input_data.dense_result.document_context
        if (
            bm25_document.workbook_hash != dense_document.workbook_hash
            or bm25_document.index_id != dense_document.index_id
        ):
            raise ModuleExecutionError(
                "BM25와 Dense 결과의 문서 또는 인덱스 컨텍스트가 일치하지 않습니다"
            )

        scores_by_query_cell: Dict[CandidateKey, float] = {}
        metadata_by_query_cell: Dict[CandidateKey, Tuple[int, RankedSearchCandidateDTO]] = {}

        branches = [
            (input_data.bm25_result, cfg.bm25_weight),
            (input_data.dense_result, cfg.dense_weight),
        ]

        for branch, weight in branches:
            if weight <= 0:
                continue
            branch_ranks: Dict[CandidateKey, int] = {}
            for candidate in branch.items:
                key = (candidate.matched_subquery, candidate.cell_id)
                previous_rank = branch_ranks.get(key)
                if previous_rank is not None and previous_rank <= candidate.rank:
                    continue
                branch_ranks[key] = candidate.rank
                current = metadata_by_query_cell.get(key)
                if current is None or candidate.rank < current[0]:
                    metadata_by_query_cell[key] = (candidate.rank, candidate)

            for key, rank in branch_ranks.items():
                scores_by_query_cell[key] = scores_by_query_cell.get(key, 0.0) + (
                    weight / (cfg.rrf_k + rank)
                )

        best_by_cell: Dict[str, Tuple[float, RankedSearchCandidateDTO]] = {}
        for key, score in scores_by_query_cell.items():
            _, cell_id = key
            candidate = metadata_by_query_cell[key][1]
            current = best_by_cell.get(cell_id)
            if current is None or score > current[0]:
                best_by_cell[cell_id] = (score, candidate)

        ranked = sorted(
            best_by_cell.values(),
            key=lambda item: (-item[0], item[1].cell_id),
        )[: cfg.top_k]

        return {
            "query_context": bm25_query.model_dump(mode="json"),
            "document_context": bm25_document.model_dump(mode="json"),
            "items": [
                {
                    "rank": rank,
                    "cell_id": candidate.cell_id,
                    "rrf_score": round(score, 10),
                    "text": candidate.text,
                    "matched_subquery": candidate.matched_subquery,
                }
                for rank, (score, candidate) in enumerate(ranked, start=1)
            ],
        }


# ==============================================================================
# 4. Exports
# ==============================================================================
__all__ = [
    "RetrievalDTO",
    "RrfCandidateDTO",
    "RrfFusionConfigDTO",
    "RrfFusionExecutionDTO",
    "RrfFusionInputDTO",
    "RrfFusionModule",
]
