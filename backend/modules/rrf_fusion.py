from typing import Any, Dict, Tuple, cast

from pydantic import BaseModel, Field

from .base import ExecutableModule, ModuleDefinition, ModuleDTO, ModuleExecutionError
from .retrieval_models import RankedSearchCandidateDTO, RankedSearchResultDTO, RetrievalDTO


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


class RrfFusionInput(ModuleDTO):
    bm25_result: RankedSearchResultDTO = Field(description="BM25 서브쿼리별 후보 순위")
    dense_result: RankedSearchResultDTO = Field(description="Dense 서브쿼리별 후보 순위")
    rrf_k: int = Field(
        default=60,
        ge=1,
        le=1000,
        description="RRF 순위 완화 상수",
    )
    top_k: int = Field(
        default=100,
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


class RrfFusionModule(ExecutableModule):
    definition = ModuleDefinition(
        type="rrf_fusion",
        label="RRF Fusion",
        category="Logic",
        description="서브쿼리별 BM25·Dense 순위를 결합한 뒤 셀 단위 최고 점수를 선택합니다.",
        inputs=["bm25_result", "dense_result"],
        outputs=["retrieval_json"],
        config_fields=["rrf_k", "top_k", "ratio_penalty"],
        raw_output=True,
        version="2",
    )
    input_model = RrfFusionInput
    output_model = RetrievalDTO

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(RrfFusionInput, payload)
        bm25_id = input_data.bm25_result.question_id.upper()
        dense_id = input_data.dense_result.question_id.upper()
        if bm25_id != dense_id:
            raise ModuleExecutionError(
                "BM25와 Dense 결과의 question_id가 일치하지 않습니다"
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
                ) + 1.0 / (input_data.rrf_k + rank)

        best_by_cell: Dict[
            str,
            Tuple[float, RankedSearchCandidateDTO],
        ] = {}
        for key, score in scores_by_query_cell.items():
            subquery, cell_id = key
            candidate = metadata_by_query_cell[key][1]
            if not _has_ratio_intent(subquery) and _is_ratio_header(candidate.text):
                score *= input_data.ratio_penalty
            current = best_by_cell.get(cell_id)
            if current is None or score > current[0]:
                best_by_cell[cell_id] = (score, candidate)

        ranked = sorted(
            best_by_cell.values(),
            key=lambda item: (-item[0], item[1].cell_id),
        )[: input_data.top_k]
        return {
            "question_id": bm25_id,
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
