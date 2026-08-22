from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.bi.models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationSource,
    BiRefreshState,
    BiSnapshotMeta,
    CompanyId,
    JobId,
    MaterializationStatus,
    RefreshStatus,
    SnapshotId,
    SnapshotStatus,
)
from backend.bi.snapshot_store import FileBiSnapshotStore


NOW = datetime(2026, 8, 19, tzinfo=UTC)


def snapshot(snapshot_id: str, workbook_hash: str) -> BiDashboardSnapshot:
    return BiDashboardSnapshot(
        schema_version=1,
        company=BiCompany(company_id="company-1", display_name="BIST"),
        source=BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash=workbook_hash,
            index_id="index-1",
        ),
        snapshot=BiSnapshotMeta(
            snapshot_id=snapshot_id,
            workbook_hash=workbook_hash,
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


def failed_job() -> BiMaterializationJob:
    return BiMaterializationJob(
        job_id="job-failed",
        company_id="company-1",
        workbook_hash="b" * 64,
        status=MaterializationStatus.FAILED,
        completed_requests=0,
        total_requests=0,
        error_code="profiling_failed",
        message="periods not found",
        started_at=NOW,
        updated_at=NOW,
    )


class FileBiSnapshotStoreTests(unittest.TestCase):
    def test_register_company_lists_entry_before_first_snapshot(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            company = BiCompany(company_id="company-1", display_name="BIST")

            # When
            store.register_company(company)

            # Then
            self.assertEqual(store.list_companies()[0].company, company)
            self.assertIsNone(store.list_companies()[0].current_snapshot_id)
            self.assertEqual(store.get_company(CompanyId("company-1")), company)

    def test_publish_makes_snapshot_current(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            expected = snapshot("snapshot-1", "a" * 64)

            # When
            store.publish(expected)

            # Then
            self.assertEqual(store.get_current(CompanyId("company-1")), expected)

    def test_publish_replaces_pointer_and_keeps_previous_snapshot(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            previous = snapshot("snapshot-1", "a" * 64)
            current = snapshot("snapshot-2", "b" * 64)
            store.publish(previous)

            # When
            store.publish(current)

            # Then
            self.assertEqual(store.get_current(CompanyId("company-1")), current)
            self.assertEqual(
                store.get_snapshot(
                    CompanyId("company-1"), SnapshotId("snapshot-1")
                ),
                previous,
            )

    def test_saving_failed_job_does_not_replace_current_snapshot(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            current = snapshot("snapshot-1", "a" * 64)
            store.publish(current)
            job = failed_job()

            # When
            store.save_job(job)

            # Then
            self.assertEqual(store.get_job(JobId("job-failed")), job)
            self.assertEqual(store.get_current(CompanyId("company-1")), current)

    def test_finds_latest_job_for_company_and_workbook(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            previous = failed_job().model_copy(
                update={"job_id": "job-previous", "workbook_hash": "a" * 64}
            )
            latest = failed_job().model_copy(
                update={
                    "job_id": "job-latest",
                    "updated_at": NOW + timedelta(minutes=1),
                }
            )
            store.save_job(previous)
            store.save_job(latest)

            # When
            company_job = store.get_latest_job(CompanyId("company-1"))
            workbook_job = store.find_latest_job(
                CompanyId("company-1"),
                "b" * 64,
            )

            # Then
            self.assertEqual(company_job, latest)
            self.assertEqual(workbook_job, latest)

    def test_server_startup_marks_interrupted_job_as_failed(self) -> None:
        # Given: a previous server stopped during extraction.
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            interrupted = failed_job().model_copy(
                update={
                    "job_id": "job-interrupted",
                    "status": MaterializationStatus.EXTRACTING,
                    "total_requests": 91,
                    "error_code": None,
                    "message": None,
                }
            )
            store.save_job(interrupted)
            recovered_at = NOW + timedelta(minutes=5)

            # When: BI services recover persisted jobs during server startup.
            recovered = store.fail_interrupted_jobs(recovered_at)

            # Then: clients receive a terminal interrupted failure.
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].status, MaterializationStatus.FAILED)
            self.assertEqual(recovered[0].error_code, "materialization_interrupted")
            self.assertEqual(recovered[0].updated_at, recovered_at)
            self.assertEqual(store.get_job(interrupted.job_id), recovered[0])


if __name__ == "__main__":
    unittest.main()
