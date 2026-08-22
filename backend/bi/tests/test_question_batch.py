from datetime import UTC, datetime
import unittest
from uuid import uuid4

from backend.bi import question_service
from backend.bi.catalog import METRIC_CATALOG, SourceMetricDefinition
from backend.bi.database_schema import BiDatabaseUnavailableError, ensure_bi_schema
from backend.bi.models import (
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    JobId,
    PeriodKind,
)
from backend.bi.question_repository import PostgresBiQuestionRepository
from backend.bi.question_records import BiQuestionStatus
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


NOW = datetime(2026, 8, 21, tzinfo=UTC)


def materialization_request() -> BiMaterializationRequest:
    return BiMaterializationRequest(
        company_id="company-task12",
        display_name="Task 12 Company",
        source=BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash="c" * 64,
            index_id="index-task12",
        ),
    )


def seven_periods() -> tuple[BiPeriod, ...]:
    return tuple(
        BiPeriod(
            period_id=f"fy-{year}",
            kind=PeriodKind.FY,
            label=f"FY{year}",
            source_label=f"FY{year - 2025}",
            end_date=None,
            ordinal=ordinal,
        )
        for ordinal, year in enumerate(range(2019, 2026), start=1)
    )


def batch_plan(job_id: str):
    plan_type = getattr(question_service, "BiQuestionBatchPlan")
    return plan_type(
        materialization=materialization_request(),
        periods=seven_periods(),
        job_id=JobId(job_id),
        created_at=NOW,
    )


class BiQuestionBatchTests(unittest.TestCase):
    def test_preserves_profile_kind_when_period_id_is_an_iso_date(self) -> None:
        # Given: the profiler returns an LTM period with a date-only identity.
        build_batch = getattr(question_service, "build_question_batch")
        plan_type = getattr(question_service, "BiQuestionBatchPlan")
        plan = plan_type(
            materialization=materialization_request(),
            periods=(
                BiPeriod(
                    period_id="2025-09-30",
                    kind=PeriodKind.LTM,
                    label="LTM",
                    source_label="LTM",
                    end_date=None,
                    ordinal=0,
                ),
            ),
            job_id=JobId("job-task12-iso-period"),
            created_at=NOW,
        )

        # When: the period is converted into persisted questions.
        batch = build_batch(plan)

        # Then: its kind remains recoverable without trusting question text.
        self.assertTrue(
            all(
                question.period_id == "ltm-2025-09-30"
                for question in batch.questions
            )
        )

    def test_builds_one_question_for_each_source_metric_and_period(self) -> None:
        # Given: the profiled workbook exposes seven financial periods.
        build_batch = getattr(question_service, "build_question_batch")
        plan = batch_plan("job-task12-count")

        # When: the materialization question batch is generated.
        batch = build_batch(plan)

        # Then: thirteen source metrics across seven periods produce 91 questions.
        source_metric_count = sum(
            isinstance(definition, SourceMetricDefinition)
            for definition in METRIC_CATALOG.values()
        )
        self.assertEqual(source_metric_count, 13)
        self.assertEqual(len(batch.questions), 91)
        self.assertTrue(
            all(
                question.status is BiQuestionStatus.QUEUED
                for question in batch.questions
            )
        )

    def test_rebuilding_same_plan_preserves_question_ids_and_order(self) -> None:
        # Given: the same job and source lineage are presented twice.
        build_batch = getattr(question_service, "build_question_batch")
        plan = batch_plan("job-task12-stable")

        # When: both batches are built independently.
        first = build_batch(plan)
        second = build_batch(plan)

        # Then: registration receives the same stable identities and order.
        self.assertEqual(first, second)
        self.assertEqual(
            len({question.question_id for question in first.questions}),
            len(first.questions),
        )


class PostgresBiQuestionBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            ensure_bi_schema()
        except BiDatabaseUnavailableError as error:
            self.skipTest(str(error))
        self.service = question_service.BiQuestionService(
            PostgresBiQuestionRepository()
        )
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

    def test_registers_same_materialization_batch_once(self) -> None:
        # Given: one profiled job is ready to enqueue its complete question set.
        job_id = f"task12-{uuid4().hex}"
        self.job_ids.append(job_id)
        plan = batch_plan(job_id)

        # When: the same materialization batch is registered twice.
        first = self.service.register_materialization_questions(plan)
        second = self.service.register_materialization_questions(plan)

        # Then: both calls return the same 91 stored rows without duplication.
        stored = self.service.list_questions(JobId(job_id))
        self.assertEqual(first, second)
        self.assertEqual(len(stored), 91)


if __name__ == "__main__":
    unittest.main()
