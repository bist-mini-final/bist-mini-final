import logging
from typing import Any, Dict, Optional

from pydantic import Field, field_validator

from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
    question_id_for,
)

logger = logging.getLogger(__name__)


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


class QueryContextOutput(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="후속 질의 파이프라인 전체에 전달할 원본 질문 컨텍스트"
    )


class QueryInputModule(BaseModule):
    definition = ModuleDefinition(
        type="query_input",
        label="Query Input",
        category="Source",
        description="자연어 질문을 받아 질문 식별자와 텍스트가 포함된 Query Context를 생성합니다.",
        inputs=[],
        outputs=["query_context"],
        config_fields=[],
        cacheable=False,
        version="3",
    )
    input_model = QueryInputDTO
    config_model = EmptyModuleConfigDTO
    output_model = QueryContextOutput

    def __init__(self) -> None:
        pass

    def execute(
        self,
        input_data: QueryInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        query_text = input_data.query
        return {
            "query_context": QueryContextDTO(
                question_id=question_id_for(query_text),
                question_text=query_text,
            ).model_dump(mode="json")
        }


__all__ = [
    "QueryContextOutput",
    "QueryInputDTO",
    "QueryInputModule",
]
