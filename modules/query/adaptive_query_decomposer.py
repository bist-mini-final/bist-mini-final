"""Use semantic routing before paying for LLM query decomposition."""

from typing import Any, Dict, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.llm.chat_completion import ChatCompletionClient
from modules.common.base_module import ExecutableModule, ModuleDefinition, ModuleInputDTO, QueryContextDTO
from backend.semantic_matching.plan_validation import validate_plan_reuse
from modules.query.decomposer import DecomposerConfigDTO, DecomposerExecutionDTO, DecomposerModule, SubqueriesDTO
from modules.query.semantic_query_matcher import SemanticQueryMatchOutput
from modules.query.subquery_format import augment_subqueries


class AdaptiveQueryDecomposerInput(ModuleInputDTO):
    query_context: QueryContextDTO
    semantic_match: SemanticQueryMatchOutput = Field(
        description="Semantic Query Matcher의 라우팅 결과"
    )


class AdaptiveQueryDecomposerConfig(DecomposerConfigDTO):
    plan_reuse_threshold: float = Field(
        default=0.80,
        ge=0,
        le=1,
        description="카탈로그 분해 계획을 재사용할 최소 시맨틱 신뢰도",
    )


class AdaptiveQueryDecomposerExecutionDTO(AdaptiveQueryDecomposerInput, AdaptiveQueryDecomposerConfig):
    """Runtime input combining graph values with the decomposer settings."""


class AdaptiveQueryDecomposerModule(ExecutableModule):
    """Avoid the decomposition call when the example-query route is confident."""

    definition = ModuleDefinition(
        type="adaptive_query_decomposer",
        label="Adaptive Query Decomposer",
        category="Logic",
        description="시맨틱 계획의 신뢰도와 질문 제약을 검증해 안전할 때만 재사용하고, 그 외에는 LLM으로 서브쿼리를 분해합니다.",
        inputs=["query_context", "semantic_match"],
        outputs=["output"],
        config_fields=[
            "model", "preset", "system_prompt", "user_prompt_template",
            "plan_reuse_threshold",
        ],
        raw_output=True,
        version="2",
    )
    input_model = AdaptiveQueryDecomposerInput
    config_model = AdaptiveQueryDecomposerConfig
    execution_model = AdaptiveQueryDecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.decomposer = DecomposerModule(completion_client=completion_client)

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(AdaptiveQueryDecomposerExecutionDTO, payload)
        # Module instances may be reused by the in-process executor. Clear
        # previous telemetry so a safe reuse is never reported as an LLM call.
        self.last_usage = None
        self.last_model = input_data.model
        match = input_data.semantic_match
        validation = validate_plan_reuse(
            input_data.query_context.question_text,
            match.target,
            match.subqueries,
        )
        if (
            match.matched
            and match.confidence >= input_data.plan_reuse_threshold
            and validation.reusable
        ):
            subqueries = augment_subqueries(match.subqueries)
            return {
                "query_context": QueryContextDTO(
                    question_id=input_data.query_context.question_id,
                    question_text=input_data.query_context.question_text,
                ).model_dump(mode="json"),
                "subqueries": subqueries,
            }
        # Low-confidence, missing, or constraint-mismatched plans must be
        # regenerated rather than silently reusing a nearby example's plan.
        result = self.decomposer.execute(
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
        self.last_usage = getattr(self.decomposer, "last_usage", None)
        self.last_model = getattr(self.decomposer, "last_model", input_data.model)
        return result
