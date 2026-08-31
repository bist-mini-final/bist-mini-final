"""밀집(Dense) 벡터 검색과 희소(Sparse/BM25) 키워드 검색의 순위 결과를 상호 순위 융합(Reciprocal Rank Fusion)하는 하이브리드 결합 모듈.

Dense 검색과 BM25 검색의 후보 순위를 `score = sum(1 / (k + rank))` 공식을 통해 융합하여,
어휘적 일치(Exact Match)와 의미론적 유사성(Semantic Similarity)의 장점을 모두 취합한 최적의 셀 후보 목록을 산출합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "dense_result": {
        "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
        "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "a1b2c3d4..."},
        "items": [
          {"rank": 1, "cell_id": "IS_C5", "score": 0.95, "text": "Company: 삼성전자 | ...", "matched_subquery": "..."}
        ]
      },
      "bm25_result": {
        "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
        "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "a1b2c3d4..."},
        "items": [
          {"rank": 1, "cell_id": "IS_C5", "score": 0.85, "text": "Company: 삼성전자 | ...", "matched_subquery": "..."}
        ]
      }
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
          "rrf_score": 0.03278,
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

CandidateKey = Tuple[str, str, str]


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
class RrfCandidateDTO(ModuleDTO):
    """Single cell candidate after Reciprocal Rank Fusion."""

    rank: int = Field(ge=1, description="RRF 결합 순위")
    index_id: str = Field(min_length=1, description="후보가 속한 collection ID")
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

    @staticmethod
    def _validate_contexts(
        input_data: RrfFusionInputDTO,
    ) -> tuple[QueryContextDTO, DocumentContextDTO]:
        bm25_query = input_data.bm25_result.query_context
        dense_query = input_data.dense_result.query_context
        if bm25_query.question_id != dense_query.question_id:
            raise ModuleExecutionError("BM25와 Dense 결과의 question_id가 일치하지 않습니다")
        bm25_document = input_data.bm25_result.document_context
        dense_document = input_data.dense_result.document_context
        if (
            bm25_document.workbook_hash != dense_document.workbook_hash
            or bm25_document.index_id != dense_document.index_id
        ):
            raise ModuleExecutionError(
                "BM25와 Dense 결과의 문서 또는 인덱스 컨텍스트가 일치하지 않습니다"
            )
        return bm25_query, bm25_document

    @staticmethod
    def _fused_candidates(
        input_data: RrfFusionInputDTO,
        cfg: RrfFusionConfigDTO,
    ) -> Dict[CandidateKey, tuple[float, RankedSearchCandidateDTO]]:
        scores: Dict[CandidateKey, float] = {}
        metadata: Dict[CandidateKey, Tuple[int, RankedSearchCandidateDTO]] = {}
        branches = (
            (input_data.bm25_result, cfg.bm25_weight),
            (input_data.dense_result, cfg.dense_weight),
        )
        for branch, weight in branches:
            if weight <= 0:
                continue
            ranks: Dict[CandidateKey, int] = {}
            for candidate in branch.items:
                key = (candidate.matched_subquery, candidate.index_id, candidate.cell_id)
                if key in ranks and ranks[key] <= candidate.rank:
                    continue
                ranks[key] = candidate.rank
                current = metadata.get(key)
                if current is None or candidate.rank < current[0]:
                    metadata[key] = (candidate.rank, candidate)
            for key, rank in ranks.items():
                scores[key] = scores.get(key, 0.0) + weight / (cfg.rrf_k + rank)
        return {key: (score, metadata[key][1]) for key, score in scores.items()}

    @staticmethod
    def _best_by_cell(
        fused: Dict[CandidateKey, tuple[float, RankedSearchCandidateDTO]],
    ) -> Dict[Tuple[str, str], Tuple[float, RankedSearchCandidateDTO]]:
        best: Dict[Tuple[str, str], Tuple[float, RankedSearchCandidateDTO]] = {}
        for (_, index_id, cell_id), value in fused.items():
            current = best.get((index_id, cell_id))
            if current is None or value[0] > current[0]:
                best[(index_id, cell_id)] = value
        return best

    def execute(
        self,
        input_data: RrfFusionInputDTO,
        config: Optional[RrfFusionConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or RrfFusionConfigDTO()
        bm25_query, bm25_document = self._validate_contexts(input_data)
        best_by_cell = self._best_by_cell(self._fused_candidates(input_data, cfg))

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
                    "index_id": candidate.index_id,
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
