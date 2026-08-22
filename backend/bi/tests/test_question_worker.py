from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.bi import composition, question_records, question_worker_main
from backend.bi.database_schema import BiDatabaseUnavailableError, ensure_bi_schema
from backend.bi.question_repository import PostgresBiQuestionRepository
from backend.bi.question_service import BiQuestionService
from backend.bi.rag_adapter import RagPipelineContractError
from backend.bi.tests.test_question_service import (
    metric_result,
    queued_question,
)
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


NOW = datetime(2026, 8, 21, tzinfo=UTC)


class FixedWorkerClock:
    def __init__(self) -> None:
        self._now_calls = 0
        self._monotonic_calls = 0

    def now(self) -> datetime:
        value = NOW + timedelta(seconds=self._now_calls)
        self._now_calls += 1
        return value

    def monotonic(self) -> float:
        values = (10.0, 11.25)
        value = values[self._monotonic_calls]
        self._monotonic_calls += 1
        return value


class InMemoryWorkerService:
    def __init__(self, question) -> None:
        self.question = question
        self.claimed = None
        self.claim = None
        self.answer = None

    def claim_next(self, command):
        self.claim = command
        if self.question is None:
            return None
        claimed = self.question.model_copy(
            update={
                "status": "running",
                "workflow_run_id": command.workflow_run_id,
                "attempt_count": 1,
                "started_at": command.claimed_at,
                "updated_at": command.claimed_at,
            }
        )
        self.claimed = claimed
        self.question = None
        return claimed

    def save_answer(self, answer):
        self.answer = answer
        return self.claimed.model_copy(
            update={
                "status": answer.outcome,
                "completed_at": answer.updated_at,
                "updated_at": answer.updated_at,
            }
        )


class SuccessfulPipeline:
    def execute(self, question):
        del question
        return metric_result()


class FailingPipeline:
    def execute(self, question):
        del question
        raise RagPipelineContractError(code="context_cells_missing")


class BiQuestionWorkerTests(unittest.TestCase):
    def test_local_one_shot_workers_use_unique_workflow_ids(self) -> None:
        worker_ids = []

        class RecordingWorker:
            def run_one(self, worker_id):
                worker_ids.append(worker_id)
                return None

        with (
            patch.dict("os.environ", {"KUBERNETES_JOB_NAME": ""}),
            patch.object(question_worker_main.socket, "gethostname", return_value="local"),
            patch.object(question_worker_main, "ChatCompletionClient"),
            patch.object(question_worker_main, "AnswerCacheRepository"),
            patch.object(question_worker_main, "ModuleRegistry"),
            patch.object(
                question_worker_main,
                "create_bi_question_worker",
                return_value=RecordingWorker(),
            ),
        ):
            question_worker_main.main()
            question_worker_main.main()

        self.assertNotEqual(worker_ids[0], worker_ids[1])
        self.assertTrue(all(str(item).startswith("local-") for item in worker_ids))

    def test_saves_completed_answer_for_one_claimed_question(self) -> None:
        # Given: one pod can atomically claim one queued question.
        worker_type = getattr(composition, "BiQuestionWorker")
        service = InMemoryWorkerService(
            queued_question("job-task13", "question-task13")
        )
        worker = worker_type(service, SuccessfulPipeline(), FixedWorkerClock())

        # When: the one-shot worker executes its single queue item.
        completed = worker.run_one("worker-task13")

        # Then: the structured answer and evidence are persisted as completed.
        self.assertIsNotNone(completed)
        self.assertEqual(service.answer.outcome, "completed")
        self.assertEqual(service.answer.result, metric_result())
        self.assertEqual(service.answer.evidence_cell_ids, ("income:B12",))
        self.assertEqual(service.answer.latency_ms, 1250)

    def test_saves_failed_answer_when_pipeline_contract_fails(self) -> None:
        # Given: a claimed question reaches a pipeline contract failure.
        worker_type = getattr(composition, "BiQuestionWorker")
        service = InMemoryWorkerService(
            queued_question("job-task13-failed", "question-task13-failed")
        )
        worker = worker_type(service, FailingPipeline(), FixedWorkerClock())

        # When: the one-shot worker handles the failure.
        failed = worker.run_one("worker-task13-failed")

        # Then: the failure is stored without a fabricated metric value.
        self.assertIsNotNone(failed)
        self.assertEqual(service.answer.outcome, "failed")
        self.assertEqual(service.answer.error_code, "context_cells_missing")
        self.assertIsNone(service.answer.result)

    def test_exits_without_pipeline_call_when_queue_is_empty(self) -> None:
        # Given: no queued BI question is available.
        worker_type = getattr(composition, "BiQuestionWorker")
        service = InMemoryWorkerService(None)
        pipeline = SuccessfulPipeline()
        worker = worker_type(service, pipeline, FixedWorkerClock())

        # When: the one-shot worker attempts one claim.
        result = worker.run_one("worker-task13-empty")

        # Then: the pod can finish successfully without an answer write.
        self.assertIsNone(result)
        self.assertIsNone(service.answer)

    def test_scaled_job_runs_one_question_per_resource_scheduled_pod(self) -> None:
        # Given: the BI worker uses the same KEDA ScaledJob pattern as jobs/.
        template_path = (
            Path(__file__).parents[1]
            / "kubernetes"
            / "bi-question-scaledjob.yaml"
        )

        # When: the deployment template is inspected as Kubernetes input.
        template = template_path.read_text(encoding="utf-8")
        normalized = " ".join(template.split())

        # Then: each scheduled pod claims one DB row and capacity limits replicas.
        self.assertIn("kind: ScaledJob", normalized)
        self.assertIn("maxReplicaCount: __MAX_REPLICAS__", normalized)
        self.assertIn("parallelism: 1", normalized)
        self.assertIn("completions: 1", normalized)
        self.assertIn("backend.bi.question_worker_main", normalized)
        self.assertIn("FROM bi_questions WHERE status = 'queued'", normalized)


class PostgresBiQuestionWorkerTests(unittest.TestCase):
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

    def test_parallel_claims_select_distinct_questions(self) -> None:
        # Given: two queued questions are visible to separate Kubernetes pods.
        claim_type = getattr(question_records, "BiQuestionClaim")
        job_id = f"task13-claim-{uuid4().hex}"
        self.job_ids.append(job_id)
        questions = (
            queued_question(job_id, f"question-{uuid4().hex}"),
            queued_question(job_id, f"question-{uuid4().hex}").model_copy(
                update={"period_id": "fy-2024"}
            ),
        )
        self.service.register_questions(
            question_records.BiQuestionBatch(questions=questions)
        )

        # When: two pods claim work concurrently.
        with ThreadPoolExecutor(max_workers=2) as executor:
            claimed = tuple(
                executor.map(
                    self.service.claim_next,
                    (
                        claim_type(
                            workflow_run_id=f"worker-{uuid4().hex}",
                            claimed_at=NOW,
                        ),
                        claim_type(
                            workflow_run_id=f"worker-{uuid4().hex}",
                            claimed_at=NOW,
                        ),
                    ),
                )
            )

        # Then: SKIP LOCKED assigns one distinct question to each pod.
        self.assertNotIn(None, claimed)
        self.assertEqual(
            len({question.question_id for question in claimed if question}),
            2,
        )

    def test_worker_persists_completed_answer_in_postgres(self) -> None:
        # Given: one real DB queue item and a deterministic local pipeline.
        worker_type = getattr(composition, "BiQuestionWorker")
        job_id = f"task13-worker-{uuid4().hex}"
        self.job_ids.append(job_id)
        question = queued_question(job_id, f"question-{uuid4().hex}")
        self.service.register_questions(
            question_records.BiQuestionBatch(questions=(question,))
        )
        worker = worker_type(
            self.service,
            SuccessfulPipeline(),
            FixedWorkerClock(),
        )

        # When: one Job pod executes one question end to end.
        completed = worker.run_one(f"worker-{uuid4().hex}")

        # Then: the question and its structured answer are committed atomically.
        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, "completed")
        stored = self.service.get_question(question.question_id)
        self.assertEqual(stored.status if stored else None, "completed")
        answers = self.service.latest_answers(
            question_records.BiLatestAnswerQuery(
                company_id=question.company_id,
                workbook_hash=question.workbook_hash,
                index_id=question.index_id,
            )
        )
        answer = next(
            stored_answer
            for stored_answer in answers
            if stored_answer.question_id == question.question_id
        )
        self.assertEqual(answer.result, metric_result())
        self.assertEqual(answer.evidence_cell_ids, ("income:B12",))


if __name__ == "__main__":
    unittest.main()
