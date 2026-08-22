from decimal import Decimal
import unittest

from backend.bi.extraction import BiMetricExtractionService
from backend.bi.extraction_models import (
    BiContextCell,
    BiMetricExtractionRequest,
    BiMetricReaderResponse,
    BiRetrievedContext,
    ReaderContractFailure,
)
from backend.bi.models import (
    AmountScale,
    BiMaterializationSource,
    MetricId,
    MetricStatus,
)


class FakeRetriever:
    def __init__(self, context: BiRetrievedContext) -> None:
        self.context = context
        self.requests = []

    def retrieve(self, request):
        self.requests.append(request)
        return self.context


class FakeReader:
    def __init__(
        self,
        response: BiMetricReaderResponse | ReaderContractFailure,
    ) -> None:
        self.response = response
        self.calls = []

    def read(self, request, context):
        self.calls.append((request, context))
        return self.response


def extraction_request(
    metric_id: MetricId = MetricId.REVENUE,
) -> BiMetricExtractionRequest:
    return BiMetricExtractionRequest(
        request_id="request-1",
        metric_id=metric_id,
        period_id="fy-2025",
        period_label="FY2025",
        source=BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash="a" * 64,
            index_id="index-1",
        ),
    )


def retrieved_context(
    *,
    request_id: str = "request-1",
    workbook_hash: str = "a" * 64,
) -> BiRetrievedContext:
    return BiRetrievedContext(
        request_id=request_id,
        file_name="company.xlsx",
        workbook_hash=workbook_hash,
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


def reader_response(
    *,
    status: MetricStatus = MetricStatus.AVAILABLE,
    raw_value: str | None = "1,234.5",
    normalized_value: Decimal | None = Decimal("1234.5"),
    currency: str | None = "USD",
    scale: AmountScale | None = AmountScale.MILLIONS,
    evidence_cell_ids: tuple[str, ...] = ("income:B12",),
    reason: str | None = None,
) -> BiMetricReaderResponse:
    return BiMetricReaderResponse(
        request_id="request-1",
        metric_id=MetricId.REVENUE,
        period_id="fy-2025",
        status=status,
        raw_value=raw_value,
        normalized_value=normalized_value,
        currency=currency,
        scale=scale,
        evidence_cell_ids=evidence_cell_ids,
        notes=(),
        reason=reason,
    )


class BiMetricExtractionServiceTests(unittest.TestCase):
    def test_extracts_available_source_metric_with_trusted_evidence(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context())
        reader = FakeReader(reader_response())
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request())

        # Then
        self.assertEqual(result.observation.status, MetricStatus.AVAILABLE)
        self.assertEqual(result.observation.normalized_value, Decimal("1234.5"))
        self.assertEqual(result.observation.evidence[0].sheet_name, "Income Statement")
        self.assertIn("FY2025", retriever.requests[0].question)

    def test_rejects_derived_metric_without_retrieval_or_llm_call(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context())
        reader = FakeReader(reader_response())
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request(MetricId.OPERATING_MARGIN))

        # Then
        self.assertEqual(result.observation.status, MetricStatus.INVALID)
        self.assertEqual(result.observation.reason, "derived_metric_requires_calculation")
        self.assertEqual(retriever.requests, [])
        self.assertEqual(reader.calls, [])

    def test_keeps_available_value_when_evidence_cell_id_is_unknown(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context())
        reader = FakeReader(reader_response(evidence_cell_ids=("fake:Z99",)))
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request())

        # Then
        self.assertEqual(result.observation.status, MetricStatus.AVAILABLE)
        self.assertEqual(result.observation.normalized_value, Decimal("1234.5"))
        self.assertEqual(result.observation.evidence, ())

    def test_converts_known_missing_tokens_to_missing_instead_of_zero(self) -> None:
        # Given
        missing_tokens = ("NA", "NM", "#PEND", None)

        for raw_value in missing_tokens:
            with self.subTest(raw_value=raw_value):
                reader = FakeReader(
                    reader_response(raw_value=raw_value, normalized_value=Decimal("0"))
                )
                service = BiMetricExtractionService(
                    FakeRetriever(retrieved_context()), reader
                )

                # When
                result = service.extract(extraction_request())

                # Then
                self.assertEqual(result.observation.status, MetricStatus.MISSING)
                self.assertIsNone(result.observation.normalized_value)

    def test_marks_amount_without_units_as_ambiguous(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context())
        reader = FakeReader(reader_response(currency=None, scale=None))
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request())

        # Then
        self.assertEqual(result.observation.status, MetricStatus.AMBIGUOUS)
        self.assertEqual(result.observation.reason, "amount_unit_ambiguous")

    def test_preserves_ambiguous_response_and_trusted_evidence(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context())
        reader = FakeReader(
            reader_response(
                status=MetricStatus.AMBIGUOUS,
                normalized_value=None,
                reason="multiple_matching_rows",
            )
        )
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request())

        # Then
        self.assertEqual(result.observation.status, MetricStatus.AMBIGUOUS)
        self.assertEqual(result.observation.reason, "multiple_matching_rows")
        self.assertEqual(result.observation.evidence[0].cell_id, "income:B12")

    def test_rejects_reader_contract_failure(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context())
        reader = FakeReader(ReaderContractFailure(code="invalid_reader_payload"))
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request())

        # Then
        self.assertEqual(result.observation.status, MetricStatus.INVALID)
        self.assertEqual(result.observation.reason, "invalid_reader_payload")

    def test_rejects_retrieval_lineage_mismatch_before_llm_call(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context(workbook_hash="b" * 64))
        reader = FakeReader(reader_response())
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request())

        # Then
        self.assertEqual(result.observation.status, MetricStatus.INVALID)
        self.assertEqual(result.observation.reason, "retrieval_lineage_mismatch")
        self.assertEqual(reader.calls, [])

    def test_rejects_reader_identity_mismatch(self) -> None:
        # Given
        retriever = FakeRetriever(retrieved_context())
        mismatched = reader_response().model_copy(update={"period_id": "fy-2024"})
        reader = FakeReader(mismatched)
        service = BiMetricExtractionService(retriever, reader)

        # When
        result = service.extract(extraction_request())

        # Then
        self.assertEqual(result.observation.status, MetricStatus.INVALID)
        self.assertEqual(result.observation.reason, "reader_identity_mismatch")


if __name__ == "__main__":
    unittest.main()
