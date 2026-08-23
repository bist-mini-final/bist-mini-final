"""사용자 자연어 질문을 입력받아 파이프라인 표준 QueryContextDTO를 생성하는 진입점 모듈.

사용자가 입력한 질의 문자열을 정규화하고, 질의 기반 결정론적 해시 ID(question_id)를 생성하여
후속 RAG 파이프라인 모듈들이 공유할 수 있는 QueryContextDTO 객체를 구성합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "query": "2023년 삼성전자 영업이익과 매출액을 알려줘"
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-c1a2b3d4e5f6",
        "question_text": "2023년 삼성전자 영업이익과 매출액을 알려줘"
      }
    }
    ```
"""

from __future__ import annotations

# ==============================================================================
# 1. Imports & Logger Setup
# ==============================================================================
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


# ==============================================================================
# 3. DTOs & Item Models
# ==============================================================================
class QueryInputDTO(ModuleInputDTO):
    """자연어 질문 입력을 위한 DTO 계약."""

    query: str = Field(
        min_length=1,
        max_length=1000,
        description="검색할 사용자의 자연어 질문 (공백 제외 1~1000자)",
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class QueryContextOutput(ModuleDTO):
    """생성된 질문 컨텍스트 출력 DTO."""

    query_context: QueryContextDTO = Field(
        description="후속 질의 파이프라인 전체에 전달할 표준 질문 컨텍스트"
    )


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class QueryInputModule(BaseModule):
    """자연어 질의를 수신하여 파이프라인 표준 컨텍스트(QueryContext)를 생성하는 모듈.

    사용자 원본 질문 문자열을 검증하고, 고유 질문 ID가 부여된 표준 `QueryContextDTO`를 반환합니다.

    Input:
        - `query` (`str`): 사용자가 입력한 자연어 질문 텍스트

    Output:
        - `query_context` (`QueryContextDTO`): 질문 식별자(question_id)와 원본 질문 텍스트가 포함된 표준 객체
    """

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


# ==============================================================================
# 5. Exports
# ==============================================================================
__all__ = [
    "QueryContextOutput",
    "QueryInputDTO",
    "QueryInputModule",
]
