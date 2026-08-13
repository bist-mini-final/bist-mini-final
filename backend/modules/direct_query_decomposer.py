"""Convert a question into one retrieval query without an LLM call.

This is intentionally separate from ``decomposer``: it is the fair baseline
used by dense, hybrid, and router experiments where query-decomposition cost
must not be included in the measurement.
"""

import hashlib
from typing import Any, Dict, cast

from pydantic import BaseModel, Field

from .base import ExecutableModule, ModuleDefinition, ModuleDTO
from .decomposer import SubqueriesDTO


class DirectQueryDecomposerInput(ModuleDTO):
    question_text: str = Field(min_length=1)


class DirectQueryDecomposerModule(ExecutableModule):
    definition = ModuleDefinition(
        type="direct_query_decomposer",
        label="Direct Query Baseline",
        category="Logic",
        description="LLM 분해 없이 원본 질문 하나를 그대로 검색 쿼리로 전달합니다.",
        inputs=["question_text"],
        outputs=["output"],
        raw_output=True,
        version="1",
    )
    input_model = DirectQueryDecomposerInput
    output_model = SubqueriesDTO

    @staticmethod
    def _question_id(question_text: str) -> str:
        normalized = " ".join(question_text.split())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16].upper()
        return f"QUERY-{digest}"

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(DirectQueryDecomposerInput, payload)
        return {
            "question_id": self._question_id(input_data.question_text),
            "subqueries": [input_data.question_text],
        }
