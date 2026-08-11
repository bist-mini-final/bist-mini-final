from typing import Any, Dict, cast

from pydantic import BaseModel, Field

from ..answer_cache import AnswerCacheRepository
from .base import ExecutableModule, ModuleDefinition, ModuleDTO
from .reader import AnswerDTO, ReaderOutput


class AnswerCacheWriterInput(ModuleDTO):
    question_text: str = Field(
        min_length=1,
        description="Query Input에서 전달된 원문 질문",
    )
    answer_json: AnswerDTO = Field(
        description="Reader가 생성한 최종 답변",
    )


class AnswerCacheWriterModule(ExecutableModule):
    definition = ModuleDefinition(
        type="answer_cache_writer",
        label="Answer Cache Writer",
        category="Output",
        description="새 Reader 답변을 질문 캐시에 저장하고 같은 답변 DTO를 전달합니다.",
        inputs=["question_text", "answer_json"],
        outputs=["answer_json"],
        config_fields=[],
        cacheable=False,
        version="1",
    )
    input_model = AnswerCacheWriterInput
    output_model = ReaderOutput

    def __init__(self, repository: AnswerCacheRepository) -> None:
        self.repository = repository

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(AnswerCacheWriterInput, payload)
        answer = input_data.answer_json
        self.repository.save_cached_answer(
            answer.question_id.upper(),
            input_data.question_text,
            answer.answer,
        )
        return {"answer_json": answer.model_dump(mode="json")}
