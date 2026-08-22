from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest
from uuid import uuid4

from backend.bi import question_repository, question_service
from backend.bi.database_schema import (
    BiDatabaseUnavailableError,
    ensure_bi_schema,
)
from backend.bi.extraction_models import BiMetricExtractionResult
from backend.bi.models import (
    AvailableObservation,
    MetricId,
    MetricStatus,
    ValueKind,
)
from backend.bi.question_records import (
    BiCompletedAnswerRecord,
    BiFailedAnswerRecord,
    BiQuestionRecord,
    BiQuestionStatus,
)
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


NOW = datetime(2026, 8, 21, tzinfo=UTC)


def queued_question(job_id: str, question_id: str) -> BiQuestionRecord:
    return BiQuestionRecord(
        question_id=question_id,
        materialization_job_id=job_id,
        company_id="company-task10",
        workbook_hash="b" * 64,
        index_id="index-task10",
        metric_id=MetricId.REVENUE,
        period_id="fy-2025",
        question_version="1",
        question_text="FY2025 revenue",
        status=BiQuestionStatus.QUEUED,
        workflow_run_id=None,
        attempt_count=0,
        created_at=NOW,
        updated_at=NOW,
        started_at=None,
        completed_at=None,
    )


def metric_result() -> BiMetricExtractionResult:
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


class PostgresBiQuestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            ensure_bi_schema()
        except BiDatabaseUnavailableError as error:
            self.skipTest(str(error))
        repository_type = getattr(
            question_repository,
            "PostgresBiQuestionRepository",
        )
        service_type = getattr(question_service, "BiQuestionService")
        self.service = service_type(repository_type())
        self.job_ids: list[str] = []

    def tearDown(self) -> None:
        if not hasattr(self, "job_ids") or not self.job_ids:
            return
        with get_pooled_raw_connection(PGVECTOR_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM bi_questions "
                    "WHERE materialization_job_id = ANY(%s)",
                    (self.job_ids,),
                )
            connection.commit()

    def new_job_id(self) -> str:
        job_id = f"task10-{uuid4().hex}"
        self.job_ids.append(job_id)
        return job_id

    def test_register_questions_is_idempotent(self) -> None:
        # Given
        batch_type = getattr(question_service, "BiQuestionBatch")
        question = queued_question(self.new_job_id(), f"question-{uuid4().hex}")
        batch = batch_type(questions=(question,))

        # When
        first = self.service.register_questions(batch)
        second = self.service.register_questions(batch)

        # Then
        self.assertEqual(first, (question,))
        self.assertEqual(second, (question,))

    def test_completed_answer_is_returned_by_latest_lookup(self) -> None:
        # Given
        batch_type = getattr(question_service, "BiQuestionBatch")
        start_type = getattr(question_service, "BiQuestionStart")
        query_type = getattr(question_service, "BiLatestAnswerQuery")
        question = queued_question(self.new_job_id(), f"question-{uuid4().hex}")
        self.service.register_questions(batch_type(questions=(question,)))
        self.service.start_question(
            start_type(
                question_id=question.question_id,
                workflow_run_id=f"run-{uuid4().hex}",
                started_at=NOW,
            )
        )
        answer = BiCompletedAnswerRecord(
            answer_id=f"answer-{uuid4().hex}",
            question_id=question.question_id,
            outcome="completed",
            answer_text="Revenue is 100.",
            result=metric_result(),
            evidence_cell_ids=("income:B12",),
            model_name="gpt-5.6-luna",
            latency_ms=1200,
            prompt_tokens=100,
            completion_tokens=20,
            created_at=NOW,
            updated_at=NOW + timedelta(seconds=2),
        )

        # When
        completed = self.service.save_answer(answer)
        latest = self.service.latest_answers(
            query_type(
                company_id=question.company_id,
                workbook_hash=question.workbook_hash,
                index_id=question.index_id,
            )
        )

        # Then
        self.assertEqual(completed.status, BiQuestionStatus.COMPLETED)
        self.assertEqual(latest, (answer,))

    def test_failed_answer_is_omitted_then_retry_updates_same_answer(self) -> None:
        # Given
        batch_type = getattr(question_service, "BiQuestionBatch")
        start_type = getattr(question_service, "BiQuestionStart")
        query_type = getattr(question_service, "BiLatestAnswerQuery")
        question = queued_question(self.new_job_id(), f"question-{uuid4().hex}")
        query = query_type(
            company_id=question.company_id,
            workbook_hash=question.workbook_hash,
            index_id=question.index_id,
        )
        self.service.register_questions(batch_type(questions=(question,)))
        self.service.start_question(
            start_type(
                question_id=question.question_id,
                workflow_run_id=f"run-{uuid4().hex}",
                started_at=NOW,
            )
        )
        failed = BiFailedAnswerRecord(
            answer_id=f"answer-{uuid4().hex}",
            question_id=question.question_id,
            outcome="failed",
            error_code="reader_timeout",
            error_message="reader timed out",
            model_name="gpt-5.6-luna",
            latency_ms=30000,
            created_at=NOW,
            updated_at=NOW + timedelta(seconds=30),
        )
        self.service.save_answer(failed)
        self.service.start_question(
            start_type(
                question_id=question.question_id,
                workflow_run_id=f"run-{uuid4().hex}",
                started_at=NOW + timedelta(minutes=1),
            )
        )
        completed = BiCompletedAnswerRecord(
            answer_id=failed.answer_id,
            question_id=question.question_id,
            outcome="completed",
            answer_text="Revenue is 100.",
            result=metric_result(),
            evidence_cell_ids=("income:B12",),
            model_name="gpt-5.6-luna",
            latency_ms=1000,
            prompt_tokens=100,
            completion_tokens=20,
            created_at=failed.created_at,
            updated_at=NOW + timedelta(minutes=1, seconds=1),
        )

        # When
        self.service.save_answer(completed)
        latest = self.service.latest_answers(query)

        # Then
        self.assertEqual(latest, (completed,))

    def test_answer_cannot_finish_a_question_that_never_started(self) -> None:
        # Given
        batch_type = getattr(question_service, "BiQuestionBatch")
        transition_error = getattr(
            question_repository,
            "BiQuestionTransitionError",
        )
        question = queued_question(self.new_job_id(), f"question-{uuid4().hex}")
        self.service.register_questions(batch_type(questions=(question,)))
        answer = BiCompletedAnswerRecord(
            answer_id=f"answer-{uuid4().hex}",
            question_id=question.question_id,
            outcome="completed",
            answer_text="Revenue is 100.",
            result=metric_result(),
            evidence_cell_ids=("income:B12",),
            model_name="gpt-5.6-luna",
            latency_ms=1000,
            prompt_tokens=100,
            completion_tokens=20,
            created_at=NOW,
            updated_at=NOW + timedelta(seconds=1),
        )

        # When / Then
        with self.assertRaises(transition_error):
            self.service.save_answer(answer)


if __name__ == "__main__":
    unittest.main()
