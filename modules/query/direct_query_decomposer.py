"""Convert a question into one retrieval query without an LLM call.

This is intentionally separate from ``decomposer``: it is the fair baseline
used by dense, hybrid, and router experiments where query-decomposition cost
must not be included in the measurement.
"""

from typing import Any, Dict, cast

from pydantic import BaseModel, Field

from modules.common.base_module import EmptyModuleConfigDTO, BaseModule, ModuleDefinition, ModuleInputDTO, QueryContextDTO
from modules.query.decomposer import SubqueriesDTO


class DirectQueryDecomposerInput(ModuleInputDTO):
    query_context: QueryContextDTO


class DirectQueryDecomposerModule(BaseModule):
    definition = ModuleDefinition(
        type="direct_query_decomposer",
        label="Direct Query Baseline",
        category="Logic",
        description="LLM 분해 없이 원본 질문 하나를 그대로 검색 쿼리로 전달합니다.",
        inputs=["query_context"],
        outputs=["output"],
        raw_output=True,
        version="1",
    )
    input_model = DirectQueryDecomposerInput
    config_model = EmptyModuleConfigDTO
    output_model = SubqueriesDTO

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(DirectQueryDecomposerInput, payload)
        return {
            "query_context": QueryContextDTO(
                question_id=input_data.query_context.question_id,
                question_text=input_data.query_context.question_text,
            ).model_dump(mode="json"),
            "subqueries": [input_data.query_context.question_text],
        }
