from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional, Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_RETRIEVAL_TOP_K, DEFAULT_RRF_K
from modules.retrieval.retrieval_models import (
    RankedSearchCandidateDTO,
    RankedSearchResultDTO,
    RetrievalDTO,
    RrfCandidateDTO,
)

logger = logging.getLogger(__name__)


CandidateKey = Tuple[str, str]


def _is_ratio_header(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in ("(x)", "/", "margin", "growth (%)")
    )


def _has_ratio_intent(subquery: str) -> bool:
    normalized = subquery.lower()
    return any(
        marker in normalized
        for marker in ("margin", "ratio", "growth", "/ ", "tev/", "price/")
    )


class RrfFusionInputDTO(ModuleInputDTO):
    bm25_result: RankedSearchResultDTO = Field(description="BM25 서브쿼리별 후보 순위")
    dense_result: RankedSearchResultDTO = Field(description="Dense 서브쿼리별 후보 순위")




class RrfFusionConfigDTO(ModuleConfigDTO):
    rrf_k: int = Field(
        default=DEFAULT_RRF_K,
        ge=1,
        le=1000,
        description="RRF 순위 완화 상수",
    )
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        gt=0,
        le=1000,
        description="결합 후 유지할 최대 셀 후보 개수",
    )
    ratio_penalty: float = Field(
        default=0.4,
        ge=0,
        le=1,
        description="비율 의도가 없는 질문에 비율 행을 적용할 감점 계수",
    )


class RrfFusionExecutionDTO(RrfFusionInputDTO, RrfFusionConfigDTO):
    """Internal union of ranked results and fusion policy."""


class RrfFusionModule(BaseModule):
    definition = ModuleDefinition(
        type="rrf_fusion",
        label="RRF Fusion",
        category="Logic",
        description="서브쿼리별 BM25·Dense 순위를 결합한 뒤 셀 단위 최고 점수를 선택합니다.",
        inputs=["bm25_result", "dense_result"],
        outputs=["retrieval_json"],
        config_fields=["rrf_k", "top_k", "ratio_penalty"],
        raw_output=True,
        version="3",
    )
    input_model = RrfFusionInputDTO
    config_model = RrfFusionConfigDTO
    execution_model = RrfFusionExecutionDTO
    output_model = RetrievalDTO

    def execute(
        self,
        input_data: RrfFusionInputDTO,
        config: Optional[RrfFusionConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, RrfFusionExecutionDTO):
            cfg = input_data
        else:
            cfg = config or RrfFusionConfigDTO()
        bm25_query = input_data.bm25_result.query_context
        dense_query = input_data.dense_result.query_context
        if bm25_query != dense_query:
            raise ModuleExecutionError(
                "BM25와 Dense 결과의 query_context가 일치하지 않습니다"
            )
        bm25_document = input_data.bm25_result.document_context
        dense_document = input_data.dense_result.document_context
        if bm25_document != dense_document:
            raise ModuleExecutionError(
                "BM25와 Dense 결과의 document_context가 일치하지 않습니다"
            )

        scores_by_query_cell: Dict[CandidateKey, float] = {}
        metadata_by_query_cell: Dict[
            CandidateKey,
            Tuple[int, RankedSearchCandidateDTO],
        ] = {}
        for branch in (input_data.bm25_result, input_data.dense_result):
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
                scores_by_query_cell[key] = scores_by_query_cell.get(
                    key,
                    0.0,
                ) + 1.0 / (cfg.rrf_k + rank)

        best_by_cell: Dict[
            str,
            Tuple[float, RankedSearchCandidateDTO],
        ] = {}
        for key, score in scores_by_query_cell.items():
            subquery, cell_id = key
            candidate = metadata_by_query_cell[key][1]
            if not _has_ratio_intent(subquery) and _is_ratio_header(candidate.text):
                score *= cfg.ratio_penalty
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
# 2. Adaptive RRF Fusion Module
# ==============================================================================

def _detect_query_intent(question_text: str) -> str:
    """Detect high-level intent from question text (quantitative / causal / trend / ratio)."""
    q = question_text.lower()
    if any(k in q for k in ["왜", "원인", "이유", "구조적", "배경", "감당할 수 있어", "영향"]):
        return "causal_reasoning"
    if any(k in q for k in ["비율", "대비", "몇 배", "비중", "마진", "%"]):
        return "ratio_calculation"
    if any(k in q for k in ["추세", "어떻게 변했", "성장", "증가", "감소", "흐름"]):
        return "trend_analysis"
    return "exact_metric_lookup"


class AdaptiveRrfFusionInputDTO(ModuleInputDTO):
    bm25_result: RankedSearchResultDTO = Field(
        description="BM25 키워드 검색 결과 입력 포트"
    )
    dense_result: RankedSearchResultDTO = Field(
        description="Dense 벡터 유사도 검색 결과 입력 포트"
    )




class AdaptiveRrfFusionConfigDTO(ModuleConfigDTO):
    rrf_k: int = Field(
        default=DEFAULT_RRF_K,
        gt=0,
        le=1000,
        description="RRF 순위 정규화 상수 k (기본값: 60)",
    )
    top_k: int = Field(
        default=200,
        gt=0,
        le=1000,
        description="최종 융합 후 Context Expander로 전달할 고유 셀 후보 수 (기본값: 200)",
    )
    adaptive_weighting: bool = Field(
        default=True,
        description="질문 의도에 따라 BM25와 Dense 가중치를 동적 조율할지 여부",
    )


class AdaptiveRrfFusionExecutionDTO(
    AdaptiveRrfFusionInputDTO, AdaptiveRrfFusionConfigDTO
):
    """Execution DTO for Adaptive RRF Fusion."""


class AdaptiveRrfFusionModule(BaseModule):
    definition = ModuleDefinition(
        type="adaptive_rrf_fusion",
        label="Adaptive RRF Fusion",
        category="Logic",
        description="질문 의도에 따라 BM25와 Dense 순위를 적응형으로 융합하여 Top-K 셀을 추출합니다.",
        inputs=["bm25_result", "dense_result"],
        outputs=["retrieval_json"],
        config_fields=["rrf_k", "top_k", "adaptive_weighting"],
        raw_output=True,
        version="1",
    )
    input_model = AdaptiveRrfFusionInputDTO
    config_model = AdaptiveRrfFusionConfigDTO
    execution_model = AdaptiveRrfFusionExecutionDTO
    output_model = RetrievalDTO

    def execute(
        self,
        input_data: AdaptiveRrfFusionInputDTO,
        config: Optional[AdaptiveRrfFusionConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, AdaptiveRrfFusionExecutionDTO):
            cfg = input_data
        else:
            cfg = config or AdaptiveRrfFusionConfigDTO()
        bm25_res = input_data.bm25_result
        dense_res = input_data.dense_result

        q_context = bm25_res.query_context
        doc_context = bm25_res.document_context

        # Determine branch weights based on intent
        w_bm25 = 1.0
        w_dense = 1.0
        if cfg.adaptive_weighting and q_context.question_text:
            intent = _detect_query_intent(q_context.question_text)
            if intent == "exact_metric_lookup":
                w_bm25 = 1.4
                w_dense = 0.8
            elif intent == "causal_reasoning":
                w_bm25 = 0.6
                w_dense = 1.5
            elif intent == "ratio_calculation":
                w_bm25 = 1.2
                w_dense = 1.0

        scores_by_query_cell: Dict[CandidateKey, float] = {}
        metadata_by_query_cell: Dict[
            CandidateKey, Tuple[int, RankedSearchCandidateDTO]
        ] = {}

        branches = [
            (bm25_res.items, w_bm25),
            (dense_res.items, w_dense),
        ]

        for items, weight in branches:
            branch_ranks: Dict[CandidateKey, int] = {}
            for candidate in items:
                key = (candidate.matched_subquery, candidate.cell_id)
                prev_rank = branch_ranks.get(key)
                if prev_rank is not None and prev_rank <= candidate.rank:
                    continue
                branch_ranks[key] = candidate.rank
                curr = metadata_by_query_cell.get(key)
                if curr is None or candidate.rank < curr[0]:
                    metadata_by_query_cell[key] = (candidate.rank, candidate)

            for key, rank in branch_ranks.items():
                scores_by_query_cell[key] = scores_by_query_cell.get(
                    key, 0.0
                ) + (weight / (cfg.rrf_k + rank))

        best_by_cell: Dict[str, Tuple[float, RankedSearchCandidateDTO]] = {}
        for key, score in scores_by_query_cell.items():
            subquery, cell_id = key
            candidate = metadata_by_query_cell[key][1]
            curr = best_by_cell.get(cell_id)
            if curr is None or score > curr[0]:
                best_by_cell[cell_id] = (score, candidate)

        ranked = sorted(
            best_by_cell.values(),
            key=lambda item: (-item[0], item[1].cell_id),
        )[: cfg.top_k]

        return {
            "query_context": q_context.model_dump(mode="json"),
            "document_context": doc_context.model_dump(mode="json"),
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

__all__ = [
    "AdaptiveRrfFusionConfigDTO",
    "AdaptiveRrfFusionExecutionDTO",
    "AdaptiveRrfFusionInputDTO",
    "AdaptiveRrfFusionModule",
    "CandidateKey",
    "RrfFusionConfigDTO",
    "RrfFusionExecutionDTO",
    "RrfFusionInputDTO",
    "RrfFusionModule",
]
