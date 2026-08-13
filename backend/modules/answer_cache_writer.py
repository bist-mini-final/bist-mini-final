from typing import Any, Dict, cast

from pydantic import BaseModel, Field

from ..answer_cache import AnswerCacheRepository
from .base import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleInputDTO,
)
from .reader import AnswerDTO, ReaderOutput


class AnswerCacheWriterInputDTO(ModuleInputDTO):
    answer_json: AnswerDTO = Field(
        description="원 질문과 문서 계보를 포함하는 Reader 최종 답변",
    )


class AnswerCacheWriterModule(ExecutableModule):
    definition = ModuleDefinition(
        type="answer_cache_writer",
        label="Answer Cache Writer",
        category="Output",
        description="Reader 답변에 포함된 Query Context를 기준으로 답변 캐시에 저장합니다.",
        inputs=["answer_json"],
        outputs=["answer_json"],
        config_fields=[],
        cacheable=False,
        version="2",
    )
    input_model = AnswerCacheWriterInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = AnswerCacheWriterInputDTO
    output_model = ReaderOutput

    def __init__(self, repository: AnswerCacheRepository) -> None:
        self.repository = repository

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(AnswerCacheWriterInputDTO, payload)
        answer = input_data.answer_json
        self.repository.save_cached_answer(
            answer.query_context.question_id.upper(),
            answer.query_context.question_text,
            answer.answer,
        )
        return {"answer_json": answer.model_dump(mode="json")}
