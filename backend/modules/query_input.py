from typing import Any, Dict, Union, cast

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from ..config import SIMILARITY_THRESHOLD
from ..answer_cache import AnswerCacheRepository
from ..similarity import rank_candidates
from .base import ExecutableModule, ModuleDefinition, ModuleDTO


class QueryInput(ModuleDTO):
    model_config = ConfigDict(extra="allow")

    query: str = Field(
        min_length=1,
        max_length=1000,
        description="검색할 사용자의 자연어 질문(공백 제외 1~1000자)",
    )
    threshold: float = Field(
        default=SIMILARITY_THRESHOLD,
        ge=0,
        le=1,
        description="캐시 질문을 일치로 판정할 최소 유사도(0~1)",
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class CachedAnswerOutput(ModuleDTO):
    cached_answer: str = Field(description="캐시에 저장된 기존 LLM 답변")


class QuestionTextOutput(ModuleDTO):
    question_text: str = Field(description="사용자가 입력한 원문 질문")


class QueryInputOutput(RootModel[Union[CachedAnswerOutput, QuestionTextOutput]]):
    """Exactly one branch DTO is returned per execution."""


class QueryInputModule(ExecutableModule):
    definition = ModuleDefinition(
        type="query_input",
        label="Query Input & Search",
        category="Source",
        description="질문을 받아 캐시 답변 또는 원문 질문 중 하나만 전달합니다.",
        inputs=[],
        outputs=["cached_answer", "question_text"],
        branch_outputs={
            "cached": "cached_answer",
            "generated": "question_text",
        },
        config_fields=["threshold"],
        cacheable=False,
    )
    input_model = QueryInput
    output_model = QueryInputOutput
    branch_output_models = {
        "cached": CachedAnswerOutput,
        "generated": QuestionTextOutput,
    }

    def __init__(self, repository: AnswerCacheRepository) -> None:
        self.repository = repository

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(QueryInput, payload)
        candidates = self.repository.question_candidates()
        if not candidates:
            return {"question_text": input_data.query}

        matches = rank_candidates(input_data.query, candidates)
        best = matches[0]
        if best.combined_score < input_data.threshold:
            return {"question_text": input_data.query}

        cached_answer = self.repository.get_cached_answer(best.question_id)
        if cached_answer is None:
            return {"question_text": input_data.query}
        return {"cached_answer": cached_answer}
