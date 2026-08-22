from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.bi.api_routes import create_bi_app
from backend.bi.api_services import BiApiServices
from backend.bi.database_schema import BiDatabaseUnavailableError, ensure_bi_schema
from backend.bi.extraction_models import BiMetricExtractionRequest
from backend.bi.models import JobId, MetricId
from backend.bi.question_batch import BiQuestionBatchPlan, build_question_batch
from backend.bi.question_pipeline import BiQuestionSourceError
from backend.bi.question_repository import PostgresBiQuestionRepository
from backend.bi.question_service import BiQuestionService
from backend.bi.question_snapshot import (
    BiPublishingQuestionService,
    BiQuestionSnapshotMaterializer,
    BiQuestionSnapshotMaterializerServices,
)
from backend.bi.question_snapshot_repository import (
    PostgresBiQuestionSnapshotRepository,
)
from backend.bi.question_worker import BiQuestionWorker
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.test_materializer import FakeExtractor, profile, request
from backend.bi.tests.test_question_snapshot_materializer import _base_snapshot
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


NOW = datetime(2026, 8, 21, tzinfo=UTC)


class AdvancingClock:
    def __init__(self) -> None:
        self._now_calls = 0
        self._monotonic_calls = 0

    def now(self) -> datetime:
        value = NOW + timedelta(seconds=self._now_calls)
        self._now_calls += 1
        return value

    def monotonic(self) -> float:
        value = float(self._monotonic_calls)
        self._monotonic_calls += 1
        return value


class DeterministicQuestionPipeline:
    def execute(self, question):
        if (
            question.metric_id is MetricId.OPERATING_INCOME
            and question.period_id == "fy-2025"
        ):
            raise BiQuestionSourceError(code="test_source_missing")
        period = next(
            item for item in profile().periods if item.period_id == question.period_id
        )
        return FakeExtractor().extract(
            BiMetricExtractionRequest(
                request_id=f"request-{question.question_id}",
                metric_id=question.metric_id,
                period_id=question.period_id,
                period_label=period.label,
                source=request().source,
            )
        )


class NoopRunner:
    def materialize(self, materialization, job_id):
        del materialization, job_id
        raise AssertionError("materialization runner must not be called")


class PostgresBiQuestionSnapshotIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            ensure_bi_schema()
        except BiDatabaseUnavailableError as error:
            self.skipTest(str(error))
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

    def test_last_worker_publishes_snapshot_visible_from_dashboard_api(self) -> None:
        # Given: a real PostgreSQL refresh queue and an existing dashboard snapshot.
        job_id = JobId(f"task15-integration-{uuid4().hex}")
        self.job_ids.append(job_id)
        batch = build_question_batch(
            BiQuestionBatchPlan(
                materialization=request(),
                periods=profile().periods,
                job_id=job_id,
                created_at=NOW,
            )
        )
        service = BiQuestionService(PostgresBiQuestionRepository())
        service.register_questions(batch)
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.publish(_base_snapshot())
            materializer = BiQuestionSnapshotMaterializer(
                BiQuestionSnapshotMaterializerServices(
                    questions=service,
                    answers=PostgresBiQuestionSnapshotRepository(),
                    store=store,
                    clock=AdvancingClock(),
                )
            )
            worker = BiQuestionWorker(
                BiPublishingQuestionService(service, materializer),
                DeterministicQuestionPipeline(),
                AdvancingClock(),
            )

            # When: one local worker execution completes each queued DB row.
            completed = tuple(
                worker.run_one(f"worker-{index}")
                for index in range(len(batch.questions))
            )

            # Then: the final commit publishes a new snapshot served by the API.
            self.assertNotIn(None, completed)
            application = create_bi_app(
                BiApiServices(
                    store=store,
                    runner=NoopRunner(),
                    clock=AdvancingClock(),
                    questions=service,
                )
            )
            response = TestClient(application).get(
                f"/api/bi/companies/{request().company_id}/dashboard"
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["refresh"]["job_id"], job_id)
            failed = body["metrics"][MetricId.OPERATING_INCOME]["observations"][1]
            self.assertEqual(failed["status"], "missing")
            self.assertIsNone(failed["normalized_value"])
            derived = body["metrics"][MetricId.OPERATING_MARGIN]["observations"][1]
            self.assertEqual(derived["status"], "missing")


if __name__ == "__main__":
    unittest.main()
