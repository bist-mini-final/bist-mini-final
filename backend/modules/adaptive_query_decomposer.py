"""Use semantic routing before paying for LLM query decomposition."""

from typing import Any, Dict, Optional, cast

from pydantic import BaseModel, Field

from ..llm.chat_completion import ChatCompletionClient
from .base import ExecutableModule, ModuleDefinition, ModuleInputDTO
from .data_lineage import QueryContextDTO
from .decomposer import DecomposerConfigDTO, DecomposerExecutionDTO, DecomposerModule, SubqueriesDTO
from .semantic_query_matcher import SemanticQueryMatchOutput


class AdaptiveQueryDecomposerInput(ModuleInputDTO):
    query_context: QueryContextDTO
    semantic_match: SemanticQueryMatchOutput = Field(
        description="Semantic Query Matcher의 라우팅 결과"
    )


class AdaptiveQueryDecomposerExecutionDTO(AdaptiveQueryDecomposerInput, DecomposerConfigDTO):
    """Runtime input combining graph values with the decomposer settings."""


class AdaptiveQueryDecomposerModule(ExecutableModule):
    """Avoid the decomposition call when the example-query route is confident."""

    definition = ModuleDefinition(
        type="adaptive_query_decomposer",
        label="Adaptive Query Decomposer",
        category="Logic",
        description="시맨틱 매칭 성공 시 원문 질문을 바로 검색하고, 실패 시에만 LLM으로 서브쿼리를 분해합니다.",
        inputs=["query_context", "semantic_match"],
        outputs=["output"],
        config_fields=["model", "preset", "system_prompt", "user_prompt_template"],
        raw_output=True,
        version="1",
    )
    input_model = AdaptiveQueryDecomposerInput
    config_model = DecomposerConfigDTO
    execution_model = AdaptiveQueryDecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.decomposer = DecomposerModule(completion_client=completion_client)

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(AdaptiveQueryDecomposerExecutionDTO, payload)
        if input_data.semantic_match.matched and input_data.semantic_match.subqueries:
            return {
                "query_context": QueryContextDTO(
                    question_id=input_data.query_context.question_id,
                    question_text=input_data.query_context.question_text,
                ).model_dump(mode="json"),
                "subqueries": input_data.semantic_match.subqueries,
            }
        if input_data.semantic_match.matched:
            # Compatibility fallback for legacy route-only catalogs. New semantic
            # plans always carry atomic subqueries and take the branch above.
            return {
                "query_context": input_data.query_context.model_dump(mode="json"),
                "subqueries": [input_data.query_context.question_text],
            }
        # Match failure is the only path that reaches the LLM decomposer.
        return self.decomposer.execute(
            DecomposerExecutionDTO(
                query_context=QueryContextDTO(
                    question_id=input_data.query_context.question_id,
                    question_text=input_data.query_context.question_text,
                ),
                model=input_data.model,
                preset=input_data.preset,
                system_prompt=input_data.system_prompt,
                user_prompt_template=input_data.user_prompt_template,
            )
        )
