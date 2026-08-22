import json
from typing import Protocol, TypeAlias, assert_never

from pydantic import ValidationError

from backend.providers.llm.chat_completion import ChatCompletionClient

from .extraction_models import (
    BiMetricExtractionRequest,
    BiMetricReaderResponse,
    BiRetrievedContext,
    MetricReaderResult,
    ReaderContractFailure,
)


JsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


def _strict_json_schema_value(value: JsonValue) -> JsonValue:
    match value:
        case dict() as schema_object:
            return _strict_json_schema(schema_object)
        case list() as schema_items:
            return [_strict_json_schema_value(item) for item in schema_items]
        case str() | int() | float() | bool() | None:
            return value
        case unreachable:
            assert_never(unreachable)


def _strict_json_schema(
    schema: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    normalized = {
        key: _strict_json_schema_value(value)
        for key, value in schema.items()
    }
    pattern = normalized.get("pattern")
    if isinstance(pattern, str) and "(?" in pattern:
        del normalized["pattern"]
    match normalized.get("properties"):
        case dict() as properties:
            normalized["required"] = list(properties)
        case str() | int() | float() | bool() | list() | None:
            pass
        case unreachable:
            assert_never(unreachable)
    return normalized


class StructuredCompletionPort(Protocol):
    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        json_schema: dict[str, JsonValue],
    ) -> str: ...


class ExistingChatCompletionAdapter:
    def __init__(self, client: ChatCompletionClient) -> None:
        self._client = client

    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        json_schema: dict[str, JsonValue],
    ) -> str:
        return self._client.complete_structured(
            model=model,
            messages=messages,
            schema_name=schema_name,
            json_schema=_strict_json_schema(json_schema),
        )


class BiMetricReader:
    def __init__(self, client: StructuredCompletionPort, model: str) -> None:
        self._client = client
        self._model = model

    def read(
        self,
        request: BiMetricExtractionRequest,
        context: BiRetrievedContext,
    ) -> MetricReaderResult:
        payload = json.dumps(
            {
                "request": {
                    "request_id": request.request_id,
                    "metric_id": request.metric_id.value,
                    "period_id": request.period_id,
                    "period_label": request.period_label,
                },
                "allowed_evidence_cells": [
                    {
                        "cell_id": cell.cell_id,
                        "sheet_name": cell.sheet_name,
                        "cell_coord": cell.cell_coord,
                        "source_text": cell.source_text,
                    }
                    for cell in context.cells
                ],
                "context_blocks": context.context_blocks,
            },
            ensure_ascii=False,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "재무 지표 한 개와 기간 한 개만 추출한다. 계산하지 않는다. "
                    "근거는 allowed_evidence_cells의 cell_id만 사용한다. "
                    "찾지 못하거나 단위가 불명확하면 상태로 표현하고 값을 0으로 만들지 않는다."
                ),
            },
            {"role": "user", "content": payload},
        ]
        raw_response = self._client.complete_structured(
            model=self._model,
            messages=messages,
            schema_name="bi_metric_extraction",
            json_schema=BiMetricReaderResponse.model_json_schema(),
        )
        try:
            return BiMetricReaderResponse.model_validate_json(raw_response)
        except ValidationError:
            return ReaderContractFailure(code="invalid_reader_payload")
