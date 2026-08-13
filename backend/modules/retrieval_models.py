from typing import List

from pydantic import Field

from .base import ModuleDTO
from .data_lineage import DocumentContextDTO, QueryContextDTO


class RankedSearchCandidateDTO(ModuleDTO):
    rank: int = Field(ge=1, description="검색기 내부 후보 순위")
    cell_id: str = Field(min_length=1, description="검색된 셀의 고유 ID")
    score: float = Field(description="해당 검색기가 계산한 원본 점수")
    text: str = Field(description="검색된 셀의 직렬화 텍스트")
    matched_subquery: str = Field(description="해당 셀과 매칭된 서브쿼리")


class RankedSearchResultDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="검색 후보가 대응하는 원본 질문 컨텍스트"
    )
    document_context: DocumentContextDTO = Field(
        description="검색 후보가 추출된 원본 문서 컨텍스트"
    )
    items: List[RankedSearchCandidateDTO] = Field(
        description="각 matched_subquery 내부 검색 점수 내림차순 후보 목록"
    )


class RrfCandidateDTO(ModuleDTO):
    rank: int = Field(ge=1, description="RRF 결합 순위")
    cell_id: str = Field(min_length=1, description="검색된 셀의 고유 ID")
    rrf_score: float = Field(gt=0, description="Reciprocal Rank Fusion 점수")
    text: str = Field(description="검색된 셀의 직렬화 텍스트")
    matched_subquery: str = Field(description="해당 셀과 매칭된 서브쿼리")


class RetrievalDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="결합 검색 결과가 대응하는 원본 질문 컨텍스트"
    )
    document_context: DocumentContextDTO = Field(
        description="결합 검색 결과가 참조하는 원본 문서 컨텍스트"
    )
    items: List[RrfCandidateDTO] = Field(description="RRF 점수 내림차순 결합 후보")
