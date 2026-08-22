from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.bi.api_routes import BiApiServices, create_bi_router
from backend.bi.materialization_models import BiMaterializationOutcome
from backend.bi.models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiRefreshState,
    BiSnapshotMeta,
    JobId,
    MaterializationStatus,
    RefreshStatus,
    SnapshotStatus,
)
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.question_api_fakes import UnusedQuestionApi


NOW = datetime(2026, 8, 20, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class UnusedRunner:
    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome:
        raise AssertionError("query endpoints must not start materialization")


class PersistedAnswerBootstrapper:
    def __init__(self, persisted: BiDashboardSnapshot) -> None:
        self._persisted = persisted
        self.requests: list[tuple[BiCompany, str]] = []

    def materialize(
        self,
        company: BiCompany,
        workbook_hash: str,
    ) -> BiDashboardSnapshot | None:
        self.requests.append((company, workbook_hash))
        return self._persisted


def create_test_app(store: FileBiSnapshotStore) -> FastAPI:
    application = FastAPI()
    application.include_router(
        create_bi_router(
            BiApiServices(
                store,
                UnusedRunner(),
                FixedClock(),
                UnusedQuestionApi(),
            )
        ),
        prefix="/api",
    )
    return application


def snapshot() -> BiDashboardSnapshot:
    return BiDashboardSnapshot(
        schema_version=1,
        company=BiCompany(company_id="company-1", display_name="BIST"),
        source=BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash="a" * 64,
            index_id="index-1",
        ),
        snapshot=BiSnapshotMeta(
            snapshot_id="snapshot-1",
            workbook_hash="a" * 64,
            status=SnapshotStatus.READY,
            generated_at=NOW,
            catalog_version="1",
            formula_version="1",
        ),
        refresh=BiRefreshState(status=RefreshStatus.IDLE),
        periods=(),
        metrics={},
        issues=(),
    )


def queued_job() -> BiMaterializationJob:
    return BiMaterializationJob(
        job_id="job-1",
        company_id="company-1",
        workbook_hash="b" * 64,
        status=MaterializationStatus.QUEUED,
        completed_requests=0,
        total_requests=0,
        started_at=NOW,
        updated_at=NOW,
    )


class BiApiQueryTests(unittest.TestCase):
    def test_newer_snapshot_clears_older_failed_job_status(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.save_job(
                queued_job().model_copy(
                    update={
                        "workbook_hash": "a" * 64,
                        "status": MaterializationStatus.FAILED,
                        "updated_at": NOW - timedelta(hours=1),
                        "error_code": "interrupted",
                        "message": "old failure",
                    }
                )
            )
            store.publish(snapshot())

            with TestClient(create_test_app(store)) as client:
                companies = client.get("/api/bi/companies")
                dashboard = client.get("/api/bi/companies/company-1/dashboard")

            self.assertEqual(
                companies.json()["companies"][0]["refresh_status"],
                "idle",
            )
            self.assertEqual(dashboard.json()["refresh"]["status"], "idle")

    def test_lists_registered_companies_with_snapshot_summary(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.publish(snapshot())

            # When
            with TestClient(create_test_app(store)) as client:
                response = client.get("/api/bi/companies")

            # Then
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["companies"][0]["company_id"], "company-1")
            self.assertEqual(
                response.json()["companies"][0]["current_snapshot_id"],
                "snapshot-1",
            )
            self.assertEqual(response.json()["companies"][0]["snapshot_status"], "ready")

    def test_returns_current_dashboard_with_snapshot_etag(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.publish(snapshot())

            # When
            with TestClient(create_test_app(store)) as client:
                response = client.get("/api/bi/companies/company-1/dashboard")

            # Then
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["snapshot"]["snapshot_id"], "snapshot-1")
            self.assertEqual(response.headers["etag"], '"snapshot-1"')

    def test_returns_pending_job_when_company_has_no_snapshot(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.register_company(BiCompany(company_id="company-1", display_name="BIST"))
            store.save_job(queued_job())

            # When
            with TestClient(create_test_app(store)) as client:
                response = client.get("/api/bi/companies/company-1/dashboard")

            # Then
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["job"]["job_id"], "job-1")
            self.assertEqual(response.json()["job"]["status"], "queued")

    def test_builds_initial_dashboard_from_persisted_answers(self) -> None:
        # Given: a company has persisted answers but no file snapshot yet.
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            company = BiCompany(company_id="company-1", display_name="BIST")
            store.register_company(company)
            job = queued_job().model_copy(update={"workbook_hash": "a" * 64})
            store.save_job(job)
            bootstrapper = PersistedAnswerBootstrapper(snapshot())
            application = FastAPI()
            application.include_router(
                create_bi_router(
                    BiApiServices(
                        store=store,
                        runner=UnusedRunner(),
                        clock=FixedClock(),
                        questions=UnusedQuestionApi(),
                        initial_snapshots=bootstrapper,
                    )
                ),
                prefix="/api",
            )

            # When: the first dashboard is requested.
            with TestClient(application) as client:
                response = client.get("/api/bi/companies/company-1/dashboard")

            # Then: the persisted-answer snapshot is returned without a runner call.
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["snapshot"]["snapshot_id"], "snapshot-1")
            self.assertEqual(bootstrapper.requests, [(company, "a" * 64)])

    def test_returns_materialization_job_and_not_found_boundaries(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.save_job(queued_job())

            # When
            with TestClient(create_test_app(store)) as client:
                found = client.get("/api/bi/materializations/job-1")
                missing_job = client.get("/api/bi/materializations/job-missing")
                missing_company = client.get(
                    "/api/bi/companies/company-missing/dashboard"
                )

            # Then
            self.assertEqual(found.status_code, 200)
            self.assertEqual(found.json()["job_id"], "job-1")
            self.assertEqual(missing_job.status_code, 404)
            self.assertEqual(missing_company.status_code, 404)


if __name__ == "__main__":
    unittest.main()
