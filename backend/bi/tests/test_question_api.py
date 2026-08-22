from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.bi import question_records
from backend.bi.api_routes import BiApiServices, create_bi_router
from backend.bi.api_services import BiQuestionApiPort
from backend.bi.database_schema import BiDatabaseUnavailableError, ensure_bi_schema
from backend.bi.materialization_models import BiMaterializationOutcome
from backend.bi.models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    BiRefreshState,
    BiSnapshotMeta,
    JobId,
    PeriodKind,
    RefreshStatus,
    SnapshotStatus,
)
from backend.bi.question_batch import BiQuestionBatchPlan
from backend.bi.question_repository import PostgresBiQuestionRepository
from backend.bi.question_service import BiQuestionService
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.test_question_service import queued_question
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


NOW = datetime(2026, 8, 21, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class UnusedRunner:
    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome:
        raise AssertionError("question API must not start legacy materialization")


class RecordingQuestionApi:
    def __init__(
        self,
        known_progress: question_records.BiQuestionJobProgress | None = None,
    ) -> None:
        self.known_progress = known_progress
        self.plans: list[BiQuestionBatchPlan] = []

    def queue_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> question_records.BiQuestionJobProgress:
        self.plans.append(plan)
        progress_type = getattr(question_records, "BiQuestionJobProgress")
        progress = progress_type(
            job_id=plan.job_id,
            total_questions=91,
            queued_questions=91,
            running_questions=0,
            completed_questions=0,
            failed_questions=0,
        )
        self.known_progress = progress
        return progress

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> question_records.BiQuestionJobProgress | None:
        progress = self.known_progress
        if progress is None or progress.job_id != job_id:
            return None
        return progress


def dashboard_snapshot(
    company_id: str = "company-task14",
    workbook_hash: str = "d" * 64,
    index_id: str = "index-task14",
) -> BiDashboardSnapshot:
    periods = tuple(
        BiPeriod(
            period_id=f"fy-{year}",
            kind=PeriodKind.FY,
            label=f"FY{year}",
            source_label=f"FY{year}",
            end_date=date(year, 12, 31),
            ordinal=ordinal,
        )
        for ordinal, year in enumerate(range(2019, 2026), start=1)
    )
    return BiDashboardSnapshot(
        schema_version=1,
        company=BiCompany(company_id=company_id, display_name="BIST"),
        source=BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash=workbook_hash,
            index_id=index_id,
        ),
        snapshot=BiSnapshotMeta(
            snapshot_id="snapshot-task14",
            workbook_hash=workbook_hash,
            status=SnapshotStatus.READY,
            generated_at=NOW,
            catalog_version="1",
            formula_version="1",
        ),
        refresh=BiRefreshState(status=RefreshStatus.IDLE),
        periods=periods,
        metrics={},
        issues=(),
    )


def create_test_app(
    store: FileBiSnapshotStore,
    questions: BiQuestionApiPort,
) -> FastAPI:
    application = FastAPI()
    application.include_router(
        create_bi_router(
            BiApiServices(store, UnusedRunner(), FixedClock(), questions)
        ),
        prefix="/api",
    )
    return application


class BiQuestionApiTests(unittest.TestCase):
    def test_refresh_queues_questions_from_current_snapshot(self) -> None:
        # Given: a company has a validated dashboard source and seven periods.
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.publish(dashboard_snapshot())
            questions = RecordingQuestionApi()

            # When: the dashboard requests a refresh.
            with TestClient(create_test_app(store, questions)) as client:
                response = client.post(
                    "/api/bi/companies/company-task14/refresh"
                )

            # Then: one 91-question job is accepted from server-owned lineage.
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["total_questions"], 91)
            self.assertEqual(response.json()["queued_questions"], 91)
            self.assertEqual(len(questions.plans), 1)
            self.assertEqual(len(questions.plans[0].periods), 7)
            self.assertEqual(
                questions.plans[0].materialization.source.index_id,
                "index-task14",
            )

    def test_returns_persisted_question_job_progress(self) -> None:
        # Given: a refresh job has mixed persisted worker states.
        progress_type = getattr(question_records, "BiQuestionJobProgress")
        progress = progress_type(
            job_id="question-job-task14",
            total_questions=91,
            queued_questions=70,
            running_questions=10,
            completed_questions=9,
            failed_questions=2,
        )
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            questions = RecordingQuestionApi(progress)

            # When: the dashboard polls the question job.
            with TestClient(create_test_app(store, questions)) as client:
                response = client.get(
                    "/api/bi/question-jobs/question-job-task14"
                )

            # Then: every status count is returned from the persisted aggregate.
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["total_questions"], 91)
            self.assertEqual(response.json()["queued_questions"], 70)
            self.assertEqual(response.json()["running_questions"], 10)
            self.assertEqual(response.json()["completed_questions"], 9)
            self.assertEqual(response.json()["failed_questions"], 2)

    def test_returns_not_found_for_unknown_question_job(self) -> None:
        # Given: no persisted question job matches the requested identifier.
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            questions = RecordingQuestionApi()

            # When: the dashboard polls an unknown job.
            with TestClient(create_test_app(store, questions)) as client:
                response = client.get(
                    "/api/bi/question-jobs/question-job-missing"
                )

            # Then: the API exposes a stable typed not-found boundary.
            self.assertEqual(response.status_code, 404)
            self.assertEqual(
                response.json()["detail"],
                "question job not found",
            )


class PostgresBiQuestionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            ensure_bi_schema()
        except BiDatabaseUnavailableError as error:
            self.skipTest(str(error))
        self.questions = BiQuestionService(PostgresBiQuestionRepository())
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

    def test_refresh_http_registers_91_questions_in_postgres(self) -> None:
        # Given: the HTTP application uses the real PostgreSQL question service.
        company_id = f"company-{uuid4().hex}"
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            store.publish(dashboard_snapshot(company_id=company_id))
            application = create_test_app(store, self.questions)

            # When: the company refresh endpoint is called once.
            with TestClient(application) as client:
                response = client.post(
                    f"/api/bi/companies/{company_id}/refresh"
                )

            # Then: PostgreSQL accepts one queued 91-question job.
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["total_questions"], 91)
            self.assertEqual(response.json()["queued_questions"], 91)
            self.job_ids.append(response.json()["job_id"])

    def test_status_http_aggregates_persisted_question_rows(self) -> None:
        # Given: PostgreSQL contains one queued and one running question.
        job_id = f"question-job-{uuid4().hex}"
        self.job_ids.append(job_id)
        queued = queued_question(job_id, f"question-{uuid4().hex}")
        running = queued_question(
            job_id,
            f"question-{uuid4().hex}",
        ).model_copy(update={"period_id": "fy-2024"})
        self.questions.register_questions(
            question_records.BiQuestionBatch(questions=(queued, running))
        )
        self.questions.start_question(
            question_records.BiQuestionStart(
                question_id=running.question_id,
                workflow_run_id=f"worker-{uuid4().hex}",
                started_at=NOW,
            )
        )
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            application = create_test_app(store, self.questions)

            # When: the persisted question job is polled over HTTP.
            with TestClient(application) as client:
                response = client.get(f"/api/bi/question-jobs/{job_id}")

            # Then: the response reflects the database status partition.
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["total_questions"], 2)
            self.assertEqual(response.json()["queued_questions"], 1)
            self.assertEqual(response.json()["running_questions"], 1)
            self.assertEqual(response.json()["completed_questions"], 0)
            self.assertEqual(response.json()["failed_questions"], 0)


if __name__ == "__main__":
    unittest.main()
