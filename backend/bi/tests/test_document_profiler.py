from hashlib import sha256
import json
import unittest

from backend.bi.document_profiler import (
    DOCUMENT_PERIOD_DISCOVERY_QUESTION,
    BiDocumentProfiler,
)
from backend.bi.extraction_models import BiContextCell, BiRetrievedContext
from backend.bi.materialization_models import BiDocumentProfile, BiProfilingFailure
from backend.bi.metric_reader import JsonValue
from backend.bi.models import BiMaterializationRequest, BiMaterializationSource
from backend.bi.profile_models import BiProfileRetrievalRequest


def materialization_request() -> BiMaterializationRequest:
    return BiMaterializationRequest(
        company_id="company-1",
        display_name="BIST",
        source=BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash="a" * 64,
            index_id="index-1",
        ),
    )


def profile_request_id() -> str:
    identity = f"company-1:{'a' * 64}:index-1"
    return "profile-" + sha256(identity.encode("utf-8")).hexdigest()[:24]


def retrieved_context(*, request_id: str | None = None) -> BiRetrievedContext:
    return BiRetrievedContext(
        request_id=request_id or profile_request_id(),
        file_name="company.xlsx",
        workbook_hash="a" * 64,
        index_id="index-1",
        context_blocks=("Income Statement FY2024 FY2025 USD millions",),
        cells=(
            BiContextCell(
                cell_id="income:B2",
                sheet_name="Income Statement",
                cell_coord="B2",
                source_text="FY2024",
            ),
            BiContextCell(
                cell_id="income:C2",
                sheet_name="Income Statement",
                cell_coord="C2",
                source_text="FY2025",
            ),
            BiContextCell(
                cell_id="income:A1",
                sheet_name="Income Statement",
                cell_coord="A1",
                source_text="USD millions",
            ),
        ),
    )


class FakeProfileRetriever:
    def __init__(self, context: BiRetrievedContext) -> None:
        self.context = context
        self.requests: list[BiProfileRetrievalRequest] = []

    def retrieve(self, request: BiProfileRetrievalRequest) -> BiRetrievedContext:
        self.requests.append(request)
        return self.context


class FakeProfileSheetCatalog:
    def list_sheets(self, source):
        del source
        return ("Income Statement", "Balance Sheet")


class FakeStructuredCompletionClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[
            tuple[str, list[dict[str, str]], str, dict[str, JsonValue]]
        ] = []

    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        json_schema: dict[str, JsonValue],
    ) -> str:
        self.calls.append((model, messages, schema_name, json_schema))
        return self.content


def valid_profile_response() -> str:
    return (
        '{"request_id":"' + profile_request_id() + '","periods":['
        '{"period":{"period_id":"fy-2024","kind":"fy","label":"FY2024",'
        '"source_label":"FY1","end_date":"2024-12-31","ordinal":0},'
        '"evidence_cell_ids":["income:B2"]},'
        '{"period":{"period_id":"fy-2025","kind":"fy","label":"FY2025",'
        '"source_label":"FY0","end_date":"2025-12-31","ordinal":1},'
        '"evidence_cell_ids":["income:C2"]}],'
        '"currency":"USD","scale":"millions",'
        '"evidence_cell_ids":["income:A1"]}'
    )


class BiDocumentProfilerTests(unittest.TestCase):
    def test_profiles_periods_units_sheets_and_trusted_evidence(self) -> None:
        # Given
        retriever = FakeProfileRetriever(retrieved_context())
        client = FakeStructuredCompletionClient(valid_profile_response())
        profiler = BiDocumentProfiler(
            retriever,
            client,
            model="fake-model",
            sheet_catalog=FakeProfileSheetCatalog(),
        )

        # When
        result = profiler.profile(materialization_request())

        # Then
        self.assertIsInstance(result, BiDocumentProfile)
        assert isinstance(result, BiDocumentProfile)
        self.assertEqual(
            [period.period_id for period in result.periods],
            ["fy-2024-12-31", "fy-2025-12-31"],
        )
        self.assertEqual(result.relevant_sheets, ("Income Statement",))
        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.scale, "millions")
        self.assertEqual(retriever.requests[0].request_id, profile_request_id())
        self.assertEqual(len(retriever.requests), 2)
        self.assertEqual(
            {item.question for item in retriever.requests},
            {DOCUMENT_PERIOD_DISCOVERY_QUESTION},
        )
        user_payload = json.loads(client.calls[0][1][1]["content"])
        self.assertEqual(
            user_payload["question"],
            DOCUMENT_PERIOD_DISCOVERY_QUESTION,
        )
        self.assertEqual(client.calls[0][2], "bi_document_profile")
        self.assertFalse(client.calls[0][3]["additionalProperties"])

    def test_keeps_profile_when_summary_evidence_cell_is_unknown(self) -> None:
        # Given
        content = valid_profile_response().replace("income:A1", "unknown:A1")
        profiler = BiDocumentProfiler(
            FakeProfileRetriever(retrieved_context()),
            FakeStructuredCompletionClient(content),
            model="fake-model",
        )

        # When
        result = profiler.profile(materialization_request())

        # Then
        self.assertIsInstance(result, BiDocumentProfile)
        assert isinstance(result, BiDocumentProfile)
        self.assertEqual(len(result.periods), 2)
        self.assertEqual(
            tuple(item.cell_id for item in result.evidence),
            ("income:B2", "income:C2"),
        )

    def test_keeps_period_when_its_evidence_cell_is_unknown(self) -> None:
        # Given: one LLM period is not backed by a retrieved cell.
        content = valid_profile_response().replace(
            '["income:C2"]}],',
            '["unknown:C2"]}],',
        )
        profiler = BiDocumentProfiler(
            FakeProfileRetriever(retrieved_context()),
            FakeStructuredCompletionClient(content),
            model="fake-model",
        )

        # When
        result = profiler.profile(materialization_request())

        # Then
        self.assertIsInstance(result, BiDocumentProfile)
        assert isinstance(result, BiDocumentProfile)
        self.assertEqual(len(result.periods), 2)
        self.assertEqual(
            tuple(item.cell_id for item in result.evidence),
            ("income:B2", "income:A1"),
        )

    def test_accepts_natural_language_periods_without_evidence_ids(self) -> None:
        # Given: the LLM finds valid periods but returns no optional evidence metadata.
        content = (
            valid_profile_response()
            .replace('["income:B2"]', '[]')
            .replace('["income:C2"]', '[]')
            .replace('["income:A1"]', '[]')
        )
        profiler = BiDocumentProfiler(
            FakeProfileRetriever(retrieved_context()),
            FakeStructuredCompletionClient(content),
            model="fake-model",
        )

        # When
        result = profiler.profile(materialization_request())

        # Then
        self.assertIsInstance(result, BiDocumentProfile)
        assert isinstance(result, BiDocumentProfile)
        self.assertEqual(len(result.periods), 2)
        self.assertEqual(result.evidence, ())

    def test_rejects_malformed_structured_response(self) -> None:
        # Given
        profiler = BiDocumentProfiler(
            FakeProfileRetriever(retrieved_context()),
            FakeStructuredCompletionClient("not-json"),
            model="fake-model",
        )

        # When
        result = profiler.profile(materialization_request())

        # Then
        self.assertEqual(
            result,
            BiProfilingFailure(
                code="invalid_profile_payload",
                message="document profile did not match the structured contract",
            ),
        )

    def test_rejects_duplicate_period_ordinals_as_typed_failure(self) -> None:
        # Given
        content = valid_profile_response().replace('"ordinal":1', '"ordinal":0')
        profiler = BiDocumentProfiler(
            FakeProfileRetriever(retrieved_context()),
            FakeStructuredCompletionClient(content),
            model="fake-model",
        )

        # When
        result = profiler.profile(materialization_request())

        # Then
        self.assertEqual(
            result,
            BiProfilingFailure(
                code="invalid_profile_payload",
                message="document profile did not match the structured contract",
            ),
        )

    def test_rejects_retrieval_lineage_mismatch(self) -> None:
        # Given
        profiler = BiDocumentProfiler(
            FakeProfileRetriever(retrieved_context(request_id="profile-wrong")),
            FakeStructuredCompletionClient(valid_profile_response()),
            model="fake-model",
        )

        # When
        result = profiler.profile(materialization_request())

        # Then
        self.assertEqual(
            result,
            BiProfilingFailure(
                code="retrieval_lineage_mismatch",
                message="retrieved profile context does not match the source request",
            ),
        )


if __name__ == "__main__":
    unittest.main()
