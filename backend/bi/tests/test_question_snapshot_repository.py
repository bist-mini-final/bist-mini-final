from datetime import UTC, datetime, timedelta
import unittest
from uuid import uuid4

from backend.bi.database_schema import BiDatabaseUnavailableError, ensure_bi_schema
from backend.bi.question_records import (
    BiCompletedAnswerRecord,
    BiQuestionBatch,
    BiQuestionStart,
)
from backend.bi.question_repository import PostgresBiQuestionRepository
from backend.bi.question_service import BiQuestionService
from backend.bi.question_snapshot_repository import (
    PostgresBiQuestionSnapshotRepository,
)
from backend.bi.tests.test_question_service import metric_result, queued_question
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


NOW = datetime(2026, 8, 21, tzinfo=UTC)


class PostgresBiQuestionSnapshotRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            ensure_bi_schema()
        except BiDatabaseUnavailableError as error:
            self.skipTest(str(error))
        self.service = BiQuestionService(PostgresBiQuestionRepository())
        self.repository = PostgresBiQuestionSnapshotRepository()
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

    def test_reads_structured_results_for_exact_materialization_job(self) -> None:
        # Given: one completed answer is stored for a refresh job.
        job_id = f"task15-repository-{uuid4().hex}"
        self.job_ids.append(job_id)
        question = queued_question(job_id, f"question-{uuid4().hex}")
        self.service.register_questions(BiQuestionBatch(questions=(question,)))
        self.service.start_question(
            BiQuestionStart(
                question_id=question.question_id,
                workflow_run_id=f"worker-{uuid4().hex}",
                started_at=NOW,
            )
        )
        self.service.save_answer(
            BiCompletedAnswerRecord(
                answer_id=f"answer-{uuid4().hex}",
                question_id=question.question_id,
                outcome="completed",
                answer_text="This prose is not used to build the dashboard.",
                result=metric_result(),
                evidence_cell_ids=("income:B12",),
                model_name="gpt-5.6-luna",
                latency_ms=100,
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            )
        )

        # When: Task 15 loads answer inputs for that exact job.
        results = self.repository.completed_results(job_id)

        # Then: only the validated answer payload is returned, not answer prose.
        self.assertEqual(results, (metric_result(),))

    def test_reads_latest_persisted_batch_for_company_workbook(self) -> None:
        # Given: one question batch has a completed structured answer.
        job_id = f"initial-snapshot-{uuid4().hex}"
        self.job_ids.append(job_id)
        question = queued_question(job_id, f"question-{uuid4().hex}")
        self.service.register_questions(BiQuestionBatch(questions=(question,)))
        self.service.start_question(
            BiQuestionStart(
                question_id=question.question_id,
                workflow_run_id=f"worker-{uuid4().hex}",
                started_at=NOW,
            )
        )
        self.service.save_answer(
            BiCompletedAnswerRecord(
                answer_id=f"answer-{uuid4().hex}",
                question_id=question.question_id,
                outcome="completed",
                answer_text="Stored answer text is not parsed by the dashboard.",
                result=metric_result(),
                evidence_cell_ids=("income:B12",),
                model_name="gpt-5.6-luna",
                latency_ms=100,
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            )
        )

        # When: the initial snapshot loader requests the latest matching batch.
        batch = self.repository.latest_batch(
            question.company_id,
            question.workbook_hash,
        )

        # Then: the persisted question and validated payload are returned together.
        self.assertIsNotNone(batch)
        self.assertEqual(batch.questions, (self.service.get_question(question.question_id),))
        self.assertEqual(batch.results, (metric_result(),))


if __name__ == "__main__":
    unittest.main()
