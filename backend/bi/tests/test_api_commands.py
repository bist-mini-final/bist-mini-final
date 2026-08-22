from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.bi.api_routes import BiApiServices, create_bi_router
from backend.bi.materialization_models import BiMaterializationOutcome
from backend.bi.models import (
    BiMaterializationJob,
    BiMaterializationRequest,
    BiMaterializationSource,
    JobId,
    MaterializationStatus,
)
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.question_api_fakes import UnusedQuestionApi


NOW = datetime(2026, 8, 20, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[BiMaterializationRequest, JobId]] = []

    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome:
        self.calls.append((request, job_id))
        return BiMaterializationOutcome(
            job=BiMaterializationJob(
                job_id=job_id,
                company_id=request.company_id,
                workbook_hash=request.source.workbook_hash,
                status=MaterializationStatus.QUEUED,
                completed_requests=0,
                total_requests=0,
                started_at=NOW,
                updated_at=NOW,
            ),
            snapshot=None,
        )


def create_test_app(store: FileBiSnapshotStore, runner: RecordingRunner) -> FastAPI:
    application = FastAPI()
    application.include_router(
        create_bi_router(
            BiApiServices(store, runner, FixedClock(), UnusedQuestionApi())
        ),
        prefix="/api",
    )
    return application


def payload(workbook_hash: str = "a" * 64) -> dict[str, str | dict[str, str]]:
    return {
        "company_id": "company-1",
        "display_name": "BIST",
        "source": {
            "file_name": "company.xlsx",
            "workbook_hash": workbook_hash,
            "index_id": "index-1",
        },
    }


def queued_job(workbook_hash: str) -> BiMaterializationJob:
    return BiMaterializationJob(
        job_id="job-existing",
        company_id="company-1",
        workbook_hash=workbook_hash,
        status=MaterializationStatus.QUEUED,
        completed_requests=0,
        total_requests=0,
        started_at=NOW,
        updated_at=NOW,
    )


class BiApiCommandTests(unittest.TestCase):
    def test_accepts_materialization_and_dispatches_background_work(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            runner = RecordingRunner()

            # When
            with TestClient(create_test_app(store, runner)) as client:
                response = client.post("/api/bi/materializations", json=payload())

            # Then
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["status"], "queued")
            self.assertTrue(response.json()["job_id"].startswith("job-"))
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(store.list_companies()[0].company.display_name, "BIST")

    def test_reuses_existing_job_for_same_company_and_hash(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            runner = RecordingRunner()
            store.save_job(queued_job("a" * 64))

            # When
            with TestClient(create_test_app(store, runner)) as client:
                response = client.post("/api/bi/materializations", json=payload())

            # Then
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["job_id"], "job-existing")
            self.assertEqual(runner.calls, [])

    def test_rejects_new_workbook_while_company_job_is_active(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            runner = RecordingRunner()
            store.save_job(queued_job("a" * 64))

            # When
            with TestClient(create_test_app(store, runner)) as client:
                response = client.post(
                    "/api/bi/materializations",
                    json=payload("b" * 64),
                )

            # Then
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "company materialization is active")
            self.assertEqual(runner.calls, [])

    def test_rejects_file_system_path_at_request_boundary(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            runner = RecordingRunner()
            invalid_payload = payload()
            source = invalid_payload["source"]
            assert isinstance(source, dict)
            source["file_name"] = "../company.xlsx"

            # When
            with TestClient(create_test_app(store, runner)) as client:
                response = client.post(
                    "/api/bi/materializations",
                    json=invalid_payload,
                )

            # Then
            self.assertEqual(response.status_code, 422)
            self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
