"""Thesaurus-augmented Decomposer module for financial spreadsheet QA."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..llm.chat_completion import (
    ChatCompletionClient,
    ChatCompletionError,
    ChatCompletionResult,
)
from ..llm.cost import calculate_openai_cost
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .data_lineage import QueryContextDTO
from .decomposer import SubqueriesDTO
from .decomposer_presets import (
    DECOMPOSER_PRESETS,
    LUNA_SYSTEM_PROMPT,
    LUNA_USER_TEMPLATE,
    decomposer_config_presets,
)
from .financial_thesaurus import format_thesaurus_prompt_guide

logger = logging.getLogger(__name__)


class ThesaurusDecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO = Field(
        description="질문 메타데이터 및 질문 본문을 포함하는 계보 DTO"
    )


class ThesaurusDecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default="gpt-5.6-luna",
        description="서브쿼리 분해에 사용할 LLM 모델 ID",
    )
    preset: str = Field(
        default="luna_thesaurus_decomposer",
        description="Decomposer 프롬프트 프리셋 ID",
    )
    system_prompt: str = Field(
        default=LUNA_SYSTEM_PROMPT,
        description="표준 시소러스 가이드가 포함된 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=LUNA_USER_TEMPLATE,
        description="{question} 템플릿 변수를 포함하는 사용자 프롬프트",
    )


class ThesaurusDecomposerExecutionDTO(
    ThesaurusDecomposerInputDTO, ThesaurusDecomposerConfigDTO
):
    """Execution DTO for Thesaurus-augmented Decomposer."""


class ThesaurusDecomposerModule(ExecutableModule):
    definition = ModuleDefinition(
        type="thesaurus_decomposer",
        label="Thesaurus Financial Decomposer",
        category="Logic",
        description="재무 지표 사전(Thesaurus)을 참조하여 질문을 정밀한 표준 서브쿼리로 분해합니다.",
        inputs=["query_context"],
        outputs=["subqueries"],
        config_fields=[
            "model",
            "preset",
            "system_prompt",
            "user_prompt_template",
        ],
        raw_output=True,
        version="1",
    )
    input_model = ThesaurusDecomposerInputDTO
    config_model = ThesaurusDecomposerConfigDTO
    execution_model = ThesaurusDecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
    ) -> None:
        self.completion_client = completion_client

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(ThesaurusDecomposerExecutionDTO, payload)
        question_text = input_data.query_context.question_text
        query_context_dict = input_data.query_context.model_dump(mode="json")

        if not question_text:
            return {
                "query_context": query_context_dict,
                "subqueries": [],
            }

        client = self.completion_client or ChatCompletionClient()

        preset_data = DECOMPOSER_PRESETS.get(input_data.preset, {})
        system_prompt = input_data.system_prompt or preset_data.get(
            "system_prompt", LUNA_SYSTEM_PROMPT
        )
        user_template = input_data.user_prompt_template or preset_data.get(
            "user_prompt_template", LUNA_USER_TEMPLATE
        )

        # Inject financial thesaurus guidance dynamically
        thesaurus_guide = format_thesaurus_prompt_guide(question_text)
        if thesaurus_guide:
            system_prompt = system_prompt + "\n" + thesaurus_guide

        user_content = user_template.format(question=question_text)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            result: ChatCompletionResult = client.complete_with_metadata(
                model=input_data.model,
                messages=messages,
            )
        except ChatCompletionError as e:
            raise ModuleExecutionError(f"LLM API 호출 실패: {e}") from e

        try:
            parsed = json.loads(result.content)
            if isinstance(parsed, list):
                subqueries_raw = parsed
            elif isinstance(parsed, dict):
                raw_val = parsed.get("subqueries", [])
                if isinstance(raw_val, str):
                    subqueries_raw = [raw_val]
                elif isinstance(raw_val, list):
                    subqueries_raw = raw_val
                else:
                    subqueries_raw = [str(raw_val)] if raw_val is not None else []
            elif isinstance(parsed, str):
                subqueries_raw = [parsed]
            else:
                subqueries_raw = [str(parsed)]
            subqueries = list(
                dict.fromkeys([str(q).strip() for q in subqueries_raw if str(q).strip()])
            )
        except json.JSONDecodeError:
            # Fallback: extract list using regex
            import re
            matches = re.findall(r'"([^"]+)"', result.content)
            subqueries = list(dict.fromkeys([m.strip() for m in matches if m.strip()]))

        self.last_usage = getattr(result, "usage", {}) or {}
        self.last_model = input_data.model
        self.last_latency = getattr(result, "latency_seconds", 0.0)

        return {
            "query_context": query_context_dict,
            "subqueries": subqueries,
        }
