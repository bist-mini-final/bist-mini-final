import unittest

from backend.bi.extraction_models import (
    BiContextCell,
    BiMetricExtractionRequest,
    BiMetricReaderResponse,
    BiRetrievedContext,
    ReaderContractFailure,
)
from backend.bi.metric_reader import (
    BiMetricReader,
    ExistingChatCompletionAdapter,
    JsonValue,
)
from backend.bi.models import BiMaterializationSource, MetricId
from backend.bi.profile_models import BiDocumentProfileReaderResponse
from backend.providers.llm.chat_completion import ChatCompletionClient


class FakeStructuredCompletionClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    def complete_structured(self, model, messages, schema_name, json_schema):
        self.calls.append((model, messages, schema_name, json_schema))
        return self.content


class CapturingChatCompletionClient(ChatCompletionClient):
    def __init__(self) -> None:
        self.json_schema: dict[str, JsonValue] | None = None

    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        json_schema: dict[str, JsonValue],
    ) -> str:
        self.json_schema = json_schema
        return "{}"


def request() -> BiMetricExtractionRequest:
    return BiMetricExtractionRequest(
        request_id="request-1",
        metric_id=MetricId.REVENUE,
        period_id="fy-2025",
        period_label="FY2025",
        source=BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash="a" * 64,
            index_id="index-1",
        ),
    )


def context() -> BiRetrievedContext:
    return BiRetrievedContext(
        request_id="request-1",
        file_name="company.xlsx",
        workbook_hash="a" * 64,
        index_id="index-1",
        context_blocks=("Income Statement | FY2025 | Revenue | 1,234.5",),
        cells=(
            BiContextCell(
                cell_id="income:B12",
                sheet_name="Income Statement",
                cell_coord="B12",
                source_text="FY2025 Revenue 1,234.5",
            ),
        ),
    )


class BiMetricReaderTests(unittest.TestCase):
    def test_adapter_removes_unsupported_decimal_lookaround_pattern(self) -> None:
        # Given
        client = CapturingChatCompletionClient()
        adapter = ExistingChatCompletionAdapter(client)

        # When
        adapter.complete_structured(
            model="fake-model",
            messages=[],
            schema_name="bi_metric_extraction",
            json_schema=BiMetricReaderResponse.model_json_schema(),
        )

        # Then
        schema = client.json_schema
        self.assertIsNotNone(schema)
        assert schema is not None
        normalized_value = schema["properties"]["normalized_value"]
        assert isinstance(normalized_value, dict)
        string_variant = normalized_value["anyOf"][1]
        assert isinstance(string_variant, dict)
        self.assertNotIn("pattern", string_variant)

    def test_adapter_marks_every_object_property_required_for_strict_schema(
        self,
    ) -> None:
        # Given
        client = CapturingChatCompletionClient()
        adapter = ExistingChatCompletionAdapter(client)

        # When
        adapter.complete_structured(
            model="fake-model",
            messages=[],
            schema_name="bi_document_profile",
            json_schema=BiDocumentProfileReaderResponse.model_json_schema(),
        )

        # Then
        schema = client.json_schema
        self.assertIsNotNone(schema)
        assert schema is not None
        self.assertEqual(
            set(schema["required"]),
            set(schema["properties"]),
        )
        period_schema = schema["$defs"]["BiPeriod"]
        assert isinstance(period_schema, dict)
        self.assertEqual(
            set(period_schema["required"]),
            set(period_schema["properties"]),
        )

    def test_reads_strict_structured_response(self) -> None:
        # Given
        client = FakeStructuredCompletionClient(
            '{"request_id":"request-1","metric_id":"revenue",'
            '"period_id":"fy-2025","status":"available",'
            '"raw_value":"1,234.5","normalized_value":"1234.5",'
            '"currency":"USD","scale":"millions",'
            '"evidence_cell_ids":["income:B12"],"notes":[],"reason":null}'
        )
        reader = BiMetricReader(client, model="fake-model")

        # When
        result = reader.read(request(), context())

        # Then
        self.assertIsInstance(result, BiMetricReaderResponse)
        self.assertEqual(client.calls[0][0], "fake-model")
        self.assertEqual(client.calls[0][2], "bi_metric_extraction")
        self.assertFalse(client.calls[0][3]["additionalProperties"])

    def test_returns_typed_failure_for_malformed_json(self) -> None:
        # Given
        reader = BiMetricReader(FakeStructuredCompletionClient("not-json"), "fake-model")

        # When
        result = reader.read(request(), context())

        # Then
        self.assertEqual(result, ReaderContractFailure(code="invalid_reader_payload"))

    def test_returns_typed_failure_for_unknown_response_field(self) -> None:
        # Given
        client = FakeStructuredCompletionClient(
            '{"request_id":"request-1","metric_id":"revenue",'
            '"period_id":"fy-2025","status":"missing","raw_value":null,'
            '"normalized_value":null,"currency":null,"scale":null,'
            '"evidence_cell_ids":[],"notes":[],"reason":"not found",'
            '"unexpected":true}'
        )
        reader = BiMetricReader(client, "fake-model")

        # When
        result = reader.read(request(), context())

        # Then
        self.assertEqual(result, ReaderContractFailure(code="invalid_reader_payload"))


if __name__ == "__main__":
    unittest.main()
