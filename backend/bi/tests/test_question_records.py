from datetime import UTC, datetime
from decimal import Decimal
import unittest

from pydantic import TypeAdapter, ValidationError

from backend.bi import question_records
from backend.bi.extraction_models import BiMetricExtractionResult
from backend.bi.models import (
    AvailableObservation,
    MetricId,
    MetricStatus,
    ValueKind,
)


NOW = datetime(2026, 8, 21, tzinfo=UTC)


def extraction_result() -> BiMetricExtractionResult:
    return BiMetricExtractionResult(
        metric_id=MetricId.REVENUE,
        period_id="fy-2025",
        value_kind=ValueKind.AMOUNT,
        currency="USD",
        scale=None,
        observation=AvailableObservation(
            period_id="fy-2025",
            status=MetricStatus.AVAILABLE,
            raw_value="100",
            normalized_value=Decimal("100"),
            evidence=(
                {
                    "cell_id": "income:B12",
                    "sheet_name": "Income",
                    "cell_coord": "B12",
                    "source_text": "FY2025 100",
                },
            ),
        ),
    )


class BiQuestionRecordTests(unittest.TestCase):
    def test_queued_question_preserves_source_and_idempotency_dimensions(self) -> None:
        # Given / When
        record_type = getattr(question_records, "BiQuestionRecord")
        record = record_type(
            question_id="question-1",
            materialization_job_id="job-1",
            company_id="company-1",
            workbook_hash="a" * 64,
            index_id="index-1",
            metric_id=MetricId.REVENUE,
            period_id="fy-2025",
            question_version="1",
            question_text="FY2025 매출은 얼마인가?",
            status="queued",
            workflow_run_id=None,
            attempt_count=0,
            created_at=NOW,
            updated_at=NOW,
            started_at=None,
            completed_at=None,
        )

        # Then
        self.assertEqual(record.workbook_hash, "a" * 64)
        self.assertEqual(record.metric_id, MetricId.REVENUE)
        self.assertIsNone(record.started_at)

    def test_running_question_requires_started_at(self) -> None:
        # Given
        record_type = getattr(question_records, "BiQuestionRecord")

        # When / Then
        with self.assertRaises(ValidationError):
            record_type(
                question_id="question-1",
                materialization_job_id="job-1",
                company_id="company-1",
                workbook_hash="a" * 64,
                index_id="index-1",
                metric_id=MetricId.REVENUE,
                period_id="fy-2025",
                question_version="1",
                question_text="FY2025 매출은 얼마인가?",
                status="running",
                attempt_count=1,
                created_at=NOW,
                updated_at=NOW,
                started_at=None,
                completed_at=None,
            )

    def test_completed_answer_requires_structured_result(self) -> None:
        # Given
        answer_adapter = TypeAdapter(getattr(question_records, "BiAnswerRecord"))

        # When / Then
        with self.assertRaises(ValidationError):
            answer_adapter.validate_python(
                {
                    "answer_id": "answer-1",
                    "question_id": "question-1",
                    "outcome": "completed",
                    "answer_text": "매출은 100입니다.",
                    "result": None,
                    "evidence_cell_ids": ["income:B12"],
                    "error_code": None,
                    "error_message": None,
                    "model_name": "gpt-5.6-luna",
                    "latency_ms": 1200,
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            )

    def test_completed_answer_keeps_typed_metric_result(self) -> None:
        # Given
        answer_adapter = TypeAdapter(getattr(question_records, "BiAnswerRecord"))

        # When
        answer = answer_adapter.validate_python(
            {
                "answer_id": "answer-1",
                "question_id": "question-1",
                "outcome": "completed",
                "answer_text": "매출은 100입니다.",
                "result": extraction_result(),
                "evidence_cell_ids": ["income:B12"],
                "error_code": None,
                "error_message": None,
                "model_name": "gpt-5.6-luna",
                "latency_ms": 1200,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )

        # Then
        self.assertEqual(answer.result.metric_id, MetricId.REVENUE)

    def test_failed_answer_preserves_error_without_fabricated_value(self) -> None:
        # Given
        answer_adapter = TypeAdapter(getattr(question_records, "BiAnswerRecord"))

        # When
        answer = answer_adapter.validate_python(
            {
                "answer_id": "answer-1",
                "question_id": "question-1",
                "outcome": "failed",
                "answer_text": None,
                "result": None,
                "evidence_cell_ids": [],
                "error_code": "reader_timeout",
                "error_message": "reader timed out",
                "model_name": "gpt-5.6-luna",
                "latency_ms": 30000,
                "prompt_tokens": None,
                "completion_tokens": None,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )

        # Then
        self.assertIsNone(answer.result)
        self.assertEqual(answer.error_code, "reader_timeout")


if __name__ == "__main__":
    unittest.main()
