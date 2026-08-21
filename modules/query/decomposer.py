import json
from typing import Any, Dict, List, Literal, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.llm.chat_completion import ChatCompletionClient, ChatCompletionError
from modules.common.base_module import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.query.decomposer_presets import (
    DECOMPOSER_PRESETS,
    LUNA_SYSTEM_PROMPT,
    LUNA_USER_TEMPLATE,
    decomposer_config_presets,
)
from modules.query.subquery_format import (
    augment_subqueries,
    normalize_subqueries,
)


class DecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO = Field(
        description="Query Input에서 전달된 질문 ID와 원문 질문",
    )


class DecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(default="gpt-5.6-luna", description="질의 분해에 사용할 LLM ID")
    preset: Literal[
        "luna_decomposer",
        "rdb_financial",
        "simple_decomposer",
    ] = Field(
        default="luna_decomposer",
        description="적용할 프롬프트 프리셋 ID",
    )
    system_prompt: str = Field(
        default=LUNA_SYSTEM_PROMPT,
        description="원자 단위 서브쿼리 생성 규칙을 정의하는 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=LUNA_USER_TEMPLATE,
        description="{question} 변수를 지원하는 사용자 프롬프트 템플릿",
    )


class DecomposerExecutionDTO(DecomposerInputDTO, DecomposerConfigDTO):
    """Internal union of the public input and module settings."""


class SubqueriesDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="서브쿼리가 파생된 원본 질문 컨텍스트"
    )
    subqueries: List[str] = Field(
        min_length=1,
        description="4필드 포맷으로 정규화·확장된 최종 검색 서브쿼리",
    )


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_subquery_response(value: str) -> List[str]:
    document = json.loads(_strip_code_fence(value))
    if isinstance(document, dict):
        document = document.get("subqueries")
    if not isinstance(document, list):
        raise ValueError("서브쿼리 응답은 JSON 배열이어야 합니다")
    return normalize_subqueries(document)


class DecomposerModule(ExecutableModule):
    definition = ModuleDefinition(
        type="decomposer",
        label="LLM Query Decomposer",
        category="Logic",
        description="질의를 원자 셀 검색용 4필드 서브쿼리로 분해합니다.",
        inputs=["query_context"],
        outputs=["output"],
        config_fields=["model", "preset", "system_prompt", "user_prompt_template"],
        config_presets=decomposer_config_presets(),
        raw_output=True,
        version="6",
    )
    input_model = DecomposerInputDTO
    config_model = DecomposerConfigDTO
    execution_model = DecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
    ) -> None:
        self.completion_client = completion_client or ChatCompletionClient()

    def _generate_subqueries(self, input_data: DecomposerExecutionDTO) -> tuple[List[str], Dict[str, int]]:
        preset = DECOMPOSER_PRESETS[input_data.preset]
        system_prompt = input_data.system_prompt or preset["system_prompt"]
        user_template = input_data.user_prompt_template or preset["user_prompt_template"]
        user_prompt = user_template.replace(
            "{question}", input_data.query_context.question_text
        )
        try:
            complete_with_meta = getattr(self.completion_client, "complete_with_metadata", None)
            if callable(complete_with_meta):
                result = complete_with_meta(
                    input_data.model,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                raw_response = result.content
                usage = result.usage
            else:
                raw_response = self.completion_client.complete(
                    input_data.model,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "reasoning_tokens": 0,
                    "total_tokens": 0,
                }
        except ChatCompletionError as error:
            raise ModuleExecutionError(str(error)) from error
        try:
            generated = _parse_subquery_response(raw_response)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise ModuleExecutionError(
                "LLM 서브쿼리 응답이 유효한 JSON 문자열 배열이 아닙니다"
            ) from error
        if not generated:
            raise ModuleExecutionError("LLM이 서브쿼리를 생성하지 않았습니다")
        return generated, usage

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(DecomposerExecutionDTO, payload)
        generated_subqueries, usage = self._generate_subqueries(input_data)
        self.last_usage = usage
        self.last_model = input_data.model
        subqueries = augment_subqueries(generated_subqueries)
        if not subqueries:
            raise ModuleExecutionError("검색용 서브쿼리 확장 결과가 비어 있습니다")

        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "subqueries": subqueries,
        }
