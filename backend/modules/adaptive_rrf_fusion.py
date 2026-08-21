"""Adaptive Intent-Aware Reciprocal Rank Fusion (RRF) Module for Financial RAG."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple, cast

from pydantic import BaseModel, Field

from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .retrieval_models import (
    RankedSearchCandidateDTO,
    RankedSearchResultDTO,
    RetrievalDTO,
    RrfCandidateDTO,
)

logger = logging.getLogger(__name__)

CandidateKey = Tuple[str, str]


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
        default=60,
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


class AdaptiveRrfFusionModule(ExecutableModule):
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

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(AdaptiveRrfFusionExecutionDTO, payload)
        bm25_res = input_data.bm25_result
        dense_res = input_data.dense_result

        q_context = bm25_res.query_context
        doc_context = bm25_res.document_context

        # Determine branch weights based on intent
        w_bm25 = 1.0
        w_dense = 1.0
        if input_data.adaptive_weighting and q_context.question_text:
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
                ) + (weight / (input_data.rrf_k + rank))

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
        )[: input_data.top_k]

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
