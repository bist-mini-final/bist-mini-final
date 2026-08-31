"""OpenAI structured-completion adapter for BI application ports."""

from backend.domains.bi.application.errors import BiProviderError
from backend.domains.bi.application.metric_reader import (
    JsonValue,
    StructuredCompletionPort,
    _strict_json_schema,
)
from backend.platform.openai.responses import OpenAIResponsesClient, OpenAIResponsesError


class BiStructuredCompletionAdapter(StructuredCompletionPort):
    def __init__(self, client: OpenAIResponsesClient) -> None:
        self._client = client

    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        json_schema: dict[str, JsonValue],
    ) -> str:
        try:
            return self._client.complete_structured(
                model=model,
                messages=messages,
                schema_name=schema_name,
                json_schema=_strict_json_schema(json_schema),
            )
        except OpenAIResponsesError as error:
            raise BiProviderError(str(error)) from error


__all__ = ["BiStructuredCompletionAdapter"]
