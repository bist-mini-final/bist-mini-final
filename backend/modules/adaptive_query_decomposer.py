"""Use semantic routing before paying for LLM query decomposition."""

from typing import Any, Dict, Optional, cast

from pydantic import BaseModel, Field

from ..chat_completion import ChatCompletionClient
from .base import ExecutableModule, ModuleDefinition, ModuleDTO
from .decomposer import DecomposerInput, DecomposerModule, SubqueriesDTO
from .semantic_query_matcher import SemanticQueryMatchOutput


class AdaptiveQueryDecomposerInput(DecomposerInput):
    semantic_match: SemanticQueryMatchOutput = Field(
        description="Semantic Query Matcher의 라우팅 결과"
    )


class AdaptiveQueryDecomposerModule(ExecutableModule):
    """Avoid the decomposition call when the example-query route is confident."""

    definition = ModuleDefinition(
        type="adaptive_query_decomposer",
        label="Adaptive Query Decomposer",
        category="Logic",
        description="시맨틱 매칭 성공 시 원문 질문을 바로 검색하고, 실패 시에만 LLM으로 서브쿼리를 분해합니다.",
        inputs=["question_text", "semantic_match"],
        outputs=["output"],
        config_fields=["model", "preset", "system_prompt", "user_prompt_template"],
        raw_output=True,
        version="1",
    )
    input_model = AdaptiveQueryDecomposerInput
    output_model = SubqueriesDTO

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.decomposer = DecomposerModule(completion_client=completion_client)

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(AdaptiveQueryDecomposerInput, payload)
        if input_data.semantic_match.matched:
            return {
                "question_id": self.decomposer._question_id(input_data.question_text),
                "subqueries": [input_data.question_text],
            }
        # Match failure is the only path that reaches the LLM decomposer.
        return self.decomposer.execute(
            DecomposerInput.model_validate(input_data.model_dump(exclude={"semantic_match"}))
        )
