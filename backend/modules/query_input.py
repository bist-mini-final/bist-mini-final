from typing import Any, Dict, Union, cast

from pydantic import BaseModel, Field, RootModel, field_validator

from ..core.settings import SIMILARITY_THRESHOLD
from ..retrieval.similarity import rank_candidates
from ..storage.answer_cache import AnswerCacheRepository
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
)
from .data_lineage import QueryContextDTO, question_id_for


class QueryInputDTO(ModuleInputDTO):
    query: str = Field(
        min_length=1,
        max_length=1000,
        description="검색할 사용자의 자연어 질문(공백 제외 1~1000자)",
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class QueryConfigDTO(ModuleConfigDTO):
    threshold: float = Field(
        default=SIMILARITY_THRESHOLD,
        ge=0,
        le=1,
        description="캐시 질문을 일치로 판정할 최소 유사도(0~1)",
    )



class QueryExecutionDTO(QueryInputDTO, QueryConfigDTO):
    """Internal validated view used only by QueryInputModule.execute."""


class CachedAnswerDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(description="캐시 답변이 대응하는 질문")
    answer: str = Field(description="캐시에 저장된 기존 LLM 답변")


class CachedAnswerOutput(ModuleDTO):
    cached_answer: CachedAnswerDTO = Field(description="질문 계보가 포함된 캐시 답변")


class QueryContextOutput(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="후속 질의 파이프라인 전체에 전달할 원본 질문 컨텍스트"
    )


class QueryInputOutput(RootModel[Union[CachedAnswerOutput, QueryContextOutput]]):
    """Exactly one branch DTO is returned per execution."""


class QueryInputModule(ExecutableModule):
    definition = ModuleDefinition(
        type="query_input",
        label="Query Input & Search",
        category="Source",
        description="질문을 받아 캐시 답변 또는 질문 식별자가 포함된 Query Context를 전달합니다.",
        inputs=[],
        outputs=["cached_answer", "query_context"],
        branch_outputs={
            "cached": "cached_answer",
            "generated": "query_context",
        },
        config_fields=["threshold"],
        cacheable=False,
        version="2",
    )
    input_model = QueryInputDTO
    config_model = QueryConfigDTO
    execution_model = QueryExecutionDTO
    output_model = QueryInputOutput
    branch_output_models = {
        "cached": CachedAnswerOutput,
        "generated": QueryContextOutput,
    }

    def __init__(self, repository: AnswerCacheRepository) -> None:
        self.repository = repository

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(QueryExecutionDTO, payload)
        query_context = {
            "question_id": question_id_for(input_data.query),
            "question_text": input_data.query,
        }
        candidates = self.repository.question_candidates()
        if not candidates:
            return {"query_context": query_context}

        matches = rank_candidates(input_data.query, candidates)
        best = matches[0]
        if best.combined_score < input_data.threshold:
            return {"query_context": query_context}

        cached_answer = self.repository.get_cached_answer(best.question_id)
        if cached_answer is None:
            return {"query_context": query_context}
        return {
            "cached_answer": {
                "query_context": {
                    "question_id": best.question_id.upper(),
                    "question_text": input_data.query,
                },
                "answer": cached_answer,
            }
        }
