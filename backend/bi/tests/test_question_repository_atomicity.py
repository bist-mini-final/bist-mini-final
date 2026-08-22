import unittest
from uuid import uuid4

from backend.bi.database_schema import (
    BiDatabaseUnavailableError,
    ensure_bi_schema,
)
from backend.bi.models import MetricId
from backend.bi.question_records import (
    BiFailedAnswerRecord,
    BiLatestAnswerQuery,
    BiQuestionBatch,
    BiQuestionStart,
)
from backend.bi.question_repository import (
    BiQuestionRegistrationError,
    PostgresBiQuestionRepository,
)
from backend.bi.question_service import BiQuestionService
from backend.bi.tests.test_question_service import NOW, queued_question
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


class PostgresBiQuestionRepositoryAtomicityTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            ensure_bi_schema()
        except BiDatabaseUnavailableError as error:
            self.skipTest(str(error))
        self.service = BiQuestionService(PostgresBiQuestionRepository())
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
        job_id = f"task10-atomic-{uuid4().hex}"
        self.job_ids.append(job_id)
        return job_id

    def test_registration_conflict_rolls_back_entire_batch(self) -> None:
        # Given
        existing = queued_question(
            self.new_job_id(),
            f"question-{uuid4().hex}",
        )
        self.service.register_questions(BiQuestionBatch(questions=(existing,)))
        conflicting_job_id = self.new_job_id()
        collision = existing.model_copy(
            update={"materialization_job_id": conflicting_job_id}
        )
        new_question = existing.model_copy(
            update={
                "question_id": f"question-{uuid4().hex}",
                "materialization_job_id": conflicting_job_id,
                "metric_id": MetricId.NET_INCOME,
            }
        )

        # When
        with self.assertRaises(BiQuestionRegistrationError):
            self.service.register_questions(
                BiQuestionBatch(questions=(collision, new_question))
            )

        # Then
        self.assertEqual(self.service.list_questions(conflicting_job_id), ())

    def test_failed_and_queued_questions_are_omitted_from_latest_answers(self) -> None:
        # Given
        job_id = self.new_job_id()
        failed_question = queued_question(job_id, f"question-{uuid4().hex}")
        queued = failed_question.model_copy(
            update={
                "question_id": f"question-{uuid4().hex}",
                "metric_id": MetricId.NET_INCOME,
            }
        )
        self.service.register_questions(
            BiQuestionBatch(questions=(failed_question, queued))
        )
        self.service.start_question(
            BiQuestionStart(
                question_id=failed_question.question_id,
                workflow_run_id=f"run-{uuid4().hex}",
                started_at=NOW,
            )
        )
        self.service.save_answer(
            BiFailedAnswerRecord(
                answer_id=f"answer-{uuid4().hex}",
                question_id=failed_question.question_id,
                outcome="failed",
                error_code="reader_timeout",
                error_message="reader timed out",
                model_name="gpt-5.6-luna",
                latency_ms=30000,
                created_at=NOW,
                updated_at=NOW,
            )
        )

        # When
        latest = self.service.latest_answers(
            BiLatestAnswerQuery(
                company_id=failed_question.company_id,
                workbook_hash=failed_question.workbook_hash,
                index_id=failed_question.index_id,
            )
        )

        # Then
        self.assertEqual(latest, ())


if __name__ == "__main__":
    unittest.main()
