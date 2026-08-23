from __future__ import annotations

import json

import httpx

from backend.providers.openai_responses import OpenAIResponsesClient


def test_responses_client_uses_official_structured_output_shape() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_123",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"answer":"done"}'}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "total_tokens": 3,
                },
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handle))
    client = OpenAIResponsesClient(api_key="test", http_client=http_client)
    try:
        result = client.create_response(
            model="gpt-5.6-luna",
            instructions="Return JSON.",
            input_items=[{"role": "user", "content": "answer"}],
            text_format={
                "type": "json_schema",
                "name": "answer",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            },
        )
    finally:
        http_client.close()

    assert result.response_id == "resp_123"
    assert result.content == '{"answer":"done"}'
    assert result.usage["prompt_tokens"] == 2
    assert captured["reasoning"] == {"effort": "none"}
    assert captured["store"] is False
    assert captured["text"] == {
        "format": {
            "type": "json_schema",
            "name": "answer",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        }
    }


def test_responses_client_extracts_function_calls() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_tool",
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_123",
                        "name": "lookup",
                        "arguments": '{"key":"value"}',
                    }
                ],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handle))
    client = OpenAIResponsesClient(api_key="test", http_client=http_client)
    try:
        result = client.create_response(
            model="gpt-5.6-luna",
            input_items=[{"role": "user", "content": "lookup"}],
            store=True,
            tools=[
                {
                    "type": "function",
                    "name": "lookup",
                    "description": "Lookup a value",
                    "parameters": {
                        "type": "object",
                        "properties": {"key": {"type": "string"}},
                        "required": ["key"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            ],
        )
    finally:
        http_client.close()

    assert result.content == ""
    assert captured["store"] is True
    assert result.function_calls == (
        {
            "call_id": "call_123",
            "name": "lookup",
            "arguments": '{"key":"value"}',
        },
    )
