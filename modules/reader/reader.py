import time
from typing import Any, Dict, List, Literal, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.llm.chat_completion import (
    ChatCompletionClient,
    ChatCompletionError,
    ChatCompletionResult,
)
from modules.common.base_module import (
    BaseModule,
    DocumentContextDTO,
    ModuleConfigDTO,
    ModuleConfigPreset,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_READER_MODEL
from modules.retrieval.context_expander import ContextDTO


READER_SYSTEM_PROMPT = """You are a rigorous data analyst and spreadsheet RAG reader.
Answer the user's question accurately and strictly based on the supplied spreadsheet cell context.

Rules:
1. State exact values, percentages, dates, and units without hallucinating or inventing missing facts.
2. Cite the supporting Sheet and Cell ID for every factual/numeric claim, for example [Sheet1:E60] or [Income_Statement:B15].
3. For comparisons or calculations, show clear and concise arithmetic steps.
4. Preserve source values such as NA, NM, or null representations as found in the raw cells.
5. If the context is insufficient or a requested metric/period is missing, explicitly state what is missing.
6. Respond in natural, professional Korean unless the user explicitly requests another language.
7. Units & Formatting: Check the cell context, column headers, and sheet metadata for applicable units (e.g. currency, %, shares, thousands, millions, count). Always state the unit clearly alongside numeric values rather than outputting ambiguous standalone numbers."""

READER_USER_TEMPLATE = """Retrieved Spreadsheet Cell Context:
{context_text}

User Question:
{question}

Grounded Answer:"""

STRICT_CITATION_SYSTEM_PROMPT = READER_SYSTEM_PROMPT + """
8. Explicitly include row header, column header, sheet name, and Cell ID in every citation sentence."""

READER_PRESETS: Dict[str, Dict[str, str]] = {
    "luna_reader": {
        "system_prompt": READER_SYSTEM_PROMPT,
        "user_prompt_template": READER_USER_TEMPLATE,
    },
    "strict_citation": {
        "system_prompt": STRICT_CITATION_SYSTEM_PROMPT,
        "user_prompt_template": READER_USER_TEMPLATE,
    },
}


def reader_config_presets() -> List[ModuleConfigPreset]:
    labels = {
        "luna_reader": "Spreadsheet Cell Reader",
        "strict_citation": "Strict Cell Citation Reader",
    }
    return [
        ModuleConfigPreset(
            id=preset_id,
            label=labels[preset_id],
            values={"preset": preset_id, **values},
        )
        for preset_id, values in READER_PRESETS.items()
    ]


class ReaderInputDTO(ModuleInputDTO):
    context_json: ContextDTO = Field(
        description=(
            "원 질문과 원본 문서 식별자를 포함하는 Context Expander의 "
            "grounded context"
        )
    )


class ReaderConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_READER_MODEL, description="답변 생성에 사용할 LLM ID"
    )
    preset: Literal["luna_reader", "strict_citation"] = Field(
        default="luna_reader",
        description="Reader 프롬프트 프리셋 ID",
    )
    system_prompt: str = Field(
        default=READER_SYSTEM_PROMPT,
        description="근거 기반 답변 규칙을 정의하는 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=READER_USER_TEMPLATE,
        description="{context_text}, {question} 변수를 지원하는 사용자 템플릿",
    )


class ReaderExecutionDTO(ReaderInputDTO, ReaderConfigDTO):
    """Internal union of grounded input and generation settings."""


class ApiUsageDTO(ModuleDTO):
    prompt_tokens: Optional[int] = Field(default=None, ge=0, description="입력 토큰 수")
    completion_tokens: Optional[int] = Field(default=None, ge=0, description="출력 토큰 수")
    cached_tokens: Optional[int] = Field(default=None, ge=0, description="캐시 적중 토큰 수")
    reasoning_tokens: Optional[int] = Field(default=None, ge=0, description="추론 토큰 수")
    total_tokens: Optional[int] = Field(default=None, ge=0, description="전체 토큰 수")


class AnswerDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="답변이 대응하는 원본 질문 컨텍스트"
    )
    document_context: DocumentContextDTO = Field(
        description="답변 근거가 추출된 원본 문서 컨텍스트"
    )
    model: str = Field(description="답변 생성에 사용된 모델 ID")
    answer: str = Field(min_length=1, description="근거 컨텍스트 기반 최종 답변")
    api_usage: ApiUsageDTO = Field(description="LLM 토큰 사용량")
    latency_seconds: float = Field(ge=0, description="Reader 실행 시간(초)")
    estimated_cost_usd: float = Field(ge=0, description="예상 API 비용(USD)")


class ReaderOutput(ModuleDTO):
    answer_json: AnswerDTO = Field(description="최종 답변 출력 포트")


class ReaderModule(BaseModule):
    definition = ModuleDefinition(
        type="reader",
        label="LLM Reader Answer",
        category="Output",
        description="질문·문서 계보가 포함된 확장 Excel 컨텍스트로 실제 LLM 답변을 생성합니다.",
        inputs=["context_json"],
        outputs=["answer_json"],
        config_fields=["model", "preset", "system_prompt", "user_prompt_template"],
        config_presets=reader_config_presets(),
        version="3",
    )
    input_model = ReaderInputDTO
    config_model = ReaderConfigDTO
    execution_model = ReaderExecutionDTO
    output_model = ReaderOutput

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
    ) -> None:
        self.completion_client = completion_client or ChatCompletionClient(
            timeout_seconds=180
        )

    @staticmethod
    def _estimated_cost(usage: Dict[str, int]) -> float:
        prompt_tokens = usage.get("prompt_tokens", 0)
        cached_tokens = min(usage.get("cached_tokens", 0), prompt_tokens)
        uncached_tokens = prompt_tokens - cached_tokens
        completion_tokens = usage.get("completion_tokens", 0)
        return (
            uncached_tokens * 1.0
            + cached_tokens * 0.1
            + completion_tokens * 6.0
        ) / 1_000_000

    def _complete(
        self,
        model: str,
        messages: list[Dict[str, str]],
    ) -> ChatCompletionResult:
        complete_with_metadata = getattr(
            self.completion_client,
            "complete_with_metadata",
            None,
        )
        if callable(complete_with_metadata):
            return complete_with_metadata(model, messages)
        started_at = time.perf_counter()
        content = self.completion_client.complete(model, messages)
        return ChatCompletionResult(
            content=content,
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 0,
            },
            latency_seconds=time.perf_counter() - started_at,
        )

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(ReaderExecutionDTO, payload)
        preset = READER_PRESETS[input_data.preset]
        system_prompt = input_data.system_prompt or preset["system_prompt"]
        user_template = input_data.user_prompt_template or preset["user_prompt_template"]
        context_text = "\n\n".join(input_data.context_json.context_blocks)
        user_prompt = user_template.replace("{context_text}", context_text).replace(
            "{question}",
            input_data.context_json.query_context.question_text,
        )
        try:
            result = self._complete(
                input_data.model,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except ChatCompletionError as error:
            raise ModuleExecutionError(str(error)) from error

        return {
            "answer_json": {
                "query_context": input_data.context_json.query_context.model_dump(
                    mode="json"
                ),
                "document_context": input_data.context_json.document_context.model_dump(
                    mode="json"
                ),
                "model": input_data.model,
                "answer": result.content,
                "api_usage": result.usage,
                "latency_seconds": round(result.latency_seconds, 3),
                "estimated_cost_usd": round(
                    self._estimated_cost(result.usage),
                    6,
                ),
            }
        }
