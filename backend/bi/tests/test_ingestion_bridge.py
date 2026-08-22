from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
import unittest

from backend.bi.api_services import BiApiServices
from backend.bi.ingestion_bridge import (
    BiIngestionCompletionHook,
    BiIndexingCompletionAdapter,
    BiWorkflowRunDispatcher,
)
from backend.bi.materialization_models import BiMaterializationOutcome
from backend.bi.materialization_scheduler import (
    BiMaterializationScheduler,
    BiScheduleStatus,
)
from backend.bi.models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiRefreshState,
    BiSnapshotMeta,
    CompanyId,
    JobId,
    MaterializationStatus,
    RefreshStatus,
    SnapshotStatus,
)
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.question_api_fakes import UnusedQuestionApi
from backend.engine.workflows.models import (
    CanvasPosition,
    NodeUI,
    RunBatchState,
    RunNodeState,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
    RunStatus,
)
from backend.engine.workflows.store import RunStore


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
        raise AssertionError((request, job_id))


def api_services(store: FileBiSnapshotStore) -> BiApiServices:
    return BiApiServices(store, UnusedRunner(), FixedClock(), UnusedQuestionApi())


class RecordingSubmitter:
    def __init__(self) -> None:
        self.calls: list[tuple[BiMaterializationRequest, JobId]] = []

    def submit(self, request: BiMaterializationRequest, job_id: JobId) -> None:
        self.calls.append((request, job_id))

    def shutdown(self, wait: bool = True) -> None:
        del wait


class CompletedExecutor:
    def __init__(self, run: WorkflowRun) -> None:
        self._run = run

    def execute_all(self, run_id: str) -> WorkflowRun:
        self._assert_run_id(run_id)
        return self._run

    def resume(self, run_id: str) -> WorkflowRun:
        self._assert_run_id(run_id)
        return self._run

    def _assert_run_id(self, run_id: str) -> None:
        if run_id != self._run.id:
            raise AssertionError(run_id)


class FailingCompletionHook:
    def handle(self, run: WorkflowRun) -> None:
        raise OSError(run.id)

    def shutdown(self, wait: bool = True) -> None:
        del wait


def completed_ingestion_run(
    *,
    status: RunStatus = "completed",
    workbook_hash: str = "a" * 64,
) -> WorkflowRun:
    nodes = (
        WorkflowNode(
            id="writer",
            module_type="pgvector_index_writer",
            position=CanvasPosition(x=0, y=0),
            config={},
            values={},
            ui=NodeUI(),
        ),
        WorkflowNode(
            id="company",
            module_type="index_company_persistence",
            position=CanvasPosition(x=1, y=0),
            config={},
            values={},
            ui=NodeUI(),
        ),
    )
    return WorkflowRun(
        id="run-indexing",
        workflow_id="indexing_pgvector",
        workflow_updated_at="2026-08-20T00:00:00Z",
        status=status,
        graph=WorkflowGraph(nodes=list(nodes), edges=[]),
        batches=[
            RunBatchState(
                index=0,
                node_ids=[node.id for node in nodes],
                status="completed" if status == "completed" else "failed",
            )
        ],
        nodes={
            "writer": RunNodeState(
                node_id="writer",
                module_type="pgvector_index_writer",
                batch_index=0,
                status="succeeded" if status == "completed" else "failed",
                output={
                    "index_id": "idx_" + ("1" * 64),
                    "file_name": "company.xlsx",
                    "workbook_hash": workbook_hash,
                    "model": "text-embedding-3-large",
                    "dimension": 3072,
                    "document_count": 100,
                },
            ),
            "company": RunNodeState(
                node_id="company",
                module_type="company_entity_extractor",
                batch_index=0,
                status="succeeded" if status == "completed" else "failed",
                output={
                    "index_id": "idx_" + ("1" * 64),
                    "company_name": "BISTelligence",
                    "ticker": "BIST",
                },
            ),
        },
    )


def published_snapshot(company_id: CompanyId) -> BiDashboardSnapshot:
    return BiDashboardSnapshot(
        schema_version=1,
        company=BiCompany(company_id=company_id, display_name="기존 기업명"),
        source=BiMaterializationSource(
            file_name="existing.xlsx",
            workbook_hash="0" * 64,
            index_id="index-existing",
        ),
        snapshot=BiSnapshotMeta(
            snapshot_id="snapshot-existing",
            workbook_hash="0" * 64,
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


class BiIngestionCompletionTests(unittest.TestCase):
    def test_schedules_materialization_when_indexing_completes(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            submitter = RecordingSubmitter()
            services = api_services(store)
            hook = BiIngestionCompletionHook(
                BiIndexingCompletionAdapter(),
                BiMaterializationScheduler(services, submitter),
            )

            # When
            result = hook.handle(completed_ingestion_run())

            # Then
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.status, BiScheduleStatus.SCHEDULED)
            self.assertEqual(len(submitter.calls), 1)
            request, job_id = submitter.calls[0]
            self.assertEqual(request.display_name, "BISTelligence")
            self.assertEqual(request.source.file_name, "company.xlsx")
            self.assertEqual(request.source.workbook_hash, "a" * 64)
            self.assertEqual(request.source.index_id, "idx_" + ("1" * 64))
            stored_job = store.get_job(job_id)
            self.assertEqual(
                stored_job.status if stored_job else None,
                MaterializationStatus.QUEUED,
            )

    def test_reuses_one_job_for_duplicate_index_completion(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            submitter = RecordingSubmitter()
            services = api_services(store)
            hook = BiIngestionCompletionHook(
                BiIndexingCompletionAdapter(),
                BiMaterializationScheduler(services, submitter),
            )
            run = completed_ingestion_run()
            hook.handle(run)

            # When
            result = hook.handle(run)

            # Then
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.status, BiScheduleStatus.REUSED)
            self.assertEqual(len(submitter.calls), 1)

    def test_does_not_schedule_materialization_when_indexing_fails(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            submitter = RecordingSubmitter()
            services = api_services(store)
            hook = BiIngestionCompletionHook(
                BiIndexingCompletionAdapter(),
                BiMaterializationScheduler(services, submitter),
            )

            # When
            result = hook.handle(completed_ingestion_run(status="failed"))

            # Then
            self.assertIsNone(result)
            self.assertEqual(submitter.calls, [])
            self.assertEqual(store.list_companies(), ())

    def test_keeps_current_snapshot_while_reuploaded_workbook_is_queued(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            submitter = RecordingSubmitter()
            services = api_services(store)
            adapter = BiIndexingCompletionAdapter()
            request = adapter.to_request(completed_ingestion_run())
            assert request is not None
            current = published_snapshot(request.company_id)
            store.publish(current)
            hook = BiIngestionCompletionHook(
                adapter,
                BiMaterializationScheduler(services, submitter),
            )

            # When
            hook.handle(completed_ingestion_run(workbook_hash="b" * 64))

            # Then
            self.assertEqual(store.get_current(request.company_id), current)

    def test_keeps_indexing_completed_when_bi_registration_fails(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            run_store = RunStore(Path(directory))
            run = completed_ingestion_run()
            run_store.save(run)
            dispatcher = BiWorkflowRunDispatcher(
                cast(Any, CompletedExecutor(run)),
                run_store,
                cast(Any, FailingCompletionHook()),
            )

            # When
            completed = dispatcher._execute(run.id, False)

            # Then
            self.assertEqual(completed.status, "completed")
            dispatcher.shutdown()


if __name__ == "__main__":
    unittest.main()
