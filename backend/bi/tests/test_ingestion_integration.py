from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from fastapi.testclient import TestClient

from backend.bi.api_routes import create_bi_app
from backend.bi.api_services import BiApiServices
from backend.bi.ingestion_bridge import create_bi_workflow_dispatcher
from backend.bi.materialization_models import BiMaterializationOutcome
from backend.bi.models import (
    BiMaterializationJob,
    BiMaterializationRequest,
    JobId,
    MaterializationStatus,
)
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.question_api_fakes import UnusedQuestionApi
from backend.bi.tests.test_ingestion_bridge import (
    CompletedExecutor,
    FixedClock,
    NOW,
    completed_ingestion_run,
)
from backend.engine.workflows.store import RunStore


class CompletingRunner:
    def __init__(self, store: FileBiSnapshotStore) -> None:
        self._store = store
        self.completed = Event()
        self.job_id: JobId | None = None

    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome:
        self.job_id = job_id
        job = BiMaterializationJob(
            job_id=job_id,
            company_id=request.company_id,
            workbook_hash=request.source.workbook_hash,
            status=MaterializationStatus.READY,
            completed_requests=1,
            total_requests=1,
            published_snapshot_id="snapshot-fake",
            started_at=NOW,
            updated_at=NOW,
        )
        self._store.save_job(job)
        self.completed.set()
        return BiMaterializationOutcome(job=job, snapshot=None)


class BiIngestionIntegrationTests(unittest.TestCase):
    def test_completed_indexing_publishes_job_state_through_bi_api(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileBiSnapshotStore(root / "bi")
            runner = CompletingRunner(store)
            services = BiApiServices(
                store,
                runner,
                FixedClock(),
                UnusedQuestionApi(),
            )
            run_store = RunStore(root / "runs")
            run = completed_ingestion_run()
            run_store.save(run)
            dispatcher = create_bi_workflow_dispatcher(
                CompletedExecutor(run),
                run_store,
                services,
            )

            # When
            dispatcher._execute(run.id, False)
            completed = runner.completed.wait(timeout=2)

            # Then
            self.assertTrue(completed)
            assert runner.job_id is not None
            with TestClient(create_bi_app(services)) as client:
                response = client.get(
                    f"/api/bi/materializations/{runner.job_id}"
                )
                companies = client.get("/api/bi/companies")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ready")
            self.assertEqual(companies.status_code, 200)
            self.assertEqual(len(companies.json()["companies"]), 1)
            dispatcher.shutdown()


if __name__ == "__main__":
    unittest.main()
