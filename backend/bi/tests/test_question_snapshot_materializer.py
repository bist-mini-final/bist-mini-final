from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.bi.extraction_models import BiMetricExtractionResult
from backend.bi.materialization_models import BiSnapshotBuildInput
from backend.bi.models import (
    AvailableObservation,
    BiEvidence,
    BiMaterializationJob,
    JobId,
    MaterializationStatus,
    MetricId,
    MetricStatus,
)
from backend.bi.question_batch import BiQuestionBatchPlan, build_question_batch
from backend.bi.question_records import BiQuestionStatus
from backend.bi.question_service import summarize_questions
from backend.bi.question_snapshot import (
    BiPublishingQuestionService,
    BiQuestionSnapshotMaterializer,
    BiQuestionSnapshotMaterializerServices,
)
from backend.bi.snapshot_builder import BiSnapshotBuilder
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.test_materializer import FakeExtractor, profile, request


NOW = datetime(2026, 8, 21, tzinfo=UTC)
REFRESH_JOB_ID = JobId("job-task15-refresh")


class FixedClock:
    def now(self) -> datetime:
        return NOW


class InMemoryQuestionService:
    def __init__(self, questions) -> None:
        self.questions = questions

    def get_job_progress(self, job_id):
        return summarize_questions(job_id, self.questions)

    def list_questions(self, job_id):
        return tuple(
            question
            for question in self.questions
            if question.materialization_job_id == job_id
        )


class InMemoryAnswerRepository:
    def __init__(self, results) -> None:
        self.results = results

    def completed_results(self, job_id):
        del job_id
        return self.results


class RecordingMaterializer:
    def __init__(self) -> None:
        self.job_ids = []

    def materialize_if_terminal(self, job_id):
        self.job_ids.append(job_id)
        return None


class RecordingQuestionService:
    def __init__(self, saved) -> None:
        self.saved = saved

    def claim_next(self, command):
        del command
        return None

    def save_answer(self, answer):
        del answer
        return self.saved


def _base_snapshot():
    extracted = tuple(
        FakeExtractor().extract(extraction)
        for extraction in _extraction_requests()
    )
    return BiSnapshotBuilder().build(
        BiSnapshotBuildInput(
            request=request(),
            job_id=JobId("job-task15-base"),
            profile=profile(),
            extracted=extracted,
            generated_at=NOW,
        )
    )


def _extraction_requests():
    from backend.bi.extraction_models import BiMetricExtractionRequest
    from backend.bi.catalog import METRIC_CATALOG, SourceMetricDefinition

    return tuple(
        BiMetricExtractionRequest(
            request_id=f"request-{metric_id.value}-{period.period_id}",
            metric_id=metric_id,
            period_id=period.period_id,
            period_label=period.label,
            source=request().source,
        )
        for metric_id, definition in METRIC_CATALOG.items()
        if isinstance(definition, SourceMetricDefinition)
        for period in profile().periods
    )


def _terminal_questions():
    batch = build_question_batch(
        BiQuestionBatchPlan(
            materialization=request(),
            periods=profile().periods,
            job_id=REFRESH_JOB_ID,
            created_at=NOW,
        )
    )
    return tuple(
        question.model_copy(
            update={
                "status": (
                    BiQuestionStatus.FAILED
                    if question.metric_id is MetricId.OPERATING_INCOME
                    and question.period_id == "fy-2025"
                    else BiQuestionStatus.COMPLETED
                ),
                "workflow_run_id": "worker-task15",
                "attempt_count": 1,
                "started_at": NOW,
                "completed_at": NOW,
            }
        )
        for question in batch.questions
    )


def _completed_results(questions):
    result_by_identity = {
        (result.metric_id, result.period_id): result
        for result in (
            FakeExtractor().extract(extraction)
            for extraction in _extraction_requests()
        )
    }
    revenue = result_by_identity[(MetricId.REVENUE, "fy-2025")]
    result_by_identity[(MetricId.REVENUE, "fy-2025")] = BiMetricExtractionResult(
        metric_id=revenue.metric_id,
        period_id=revenue.period_id,
        value_kind=revenue.value_kind,
        currency=revenue.currency,
        scale=revenue.scale,
        observation=AvailableObservation(
            period_id=revenue.period_id,
            status=MetricStatus.AVAILABLE,
            raw_value="150",
            normalized_value=Decimal("150"),
            evidence=(
                BiEvidence(
                    cell_id="income:C12",
                    sheet_name="Income Statement",
                    cell_coord="C12",
                    source_text="Revenue 150",
                ),
            ),
        ),
    )
    return tuple(
        result_by_identity[(question.metric_id, question.period_id)]
        for question in questions
        if question.status is BiQuestionStatus.COMPLETED
    )


class BiQuestionSnapshotMaterializerTests(unittest.TestCase):
    def test_terminal_initial_job_waits_for_dashboard_bootstrap(self) -> None:
        # Given: the first persisted answer batch is terminal before a snapshot exists.
        questions = _terminal_questions()
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            materializer = BiQuestionSnapshotMaterializer(
                BiQuestionSnapshotMaterializerServices(
                    questions=InMemoryQuestionService(questions),
                    answers=InMemoryAnswerRepository(_completed_results(questions)),
                    store=store,
                    clock=FixedClock(),
                )
            )

            # When: the last worker checks whether it can publish a refresh.
            refreshed = materializer.materialize_if_terminal(REFRESH_JOB_ID)

            # Then: initial publication is left to the persisted-answer bootstrap.
            self.assertIsNone(refreshed)

    def test_terminal_job_publishes_answer_backed_snapshot_with_failures_as_na(self) -> None:
        # Given: every question is terminal and one answer failed.
        questions = _terminal_questions()
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            base = _base_snapshot()
            store.publish(base)
            store.save_job(
                BiMaterializationJob(
                    job_id=REFRESH_JOB_ID,
                    company_id=request().company_id,
                    workbook_hash=request().source.workbook_hash,
                    status=MaterializationStatus.EXTRACTING,
                    completed_requests=0,
                    total_requests=len(questions),
                    started_at=NOW,
                    updated_at=NOW,
                )
            )
            materializer = BiQuestionSnapshotMaterializer(
                BiQuestionSnapshotMaterializerServices(
                    questions=InMemoryQuestionService(questions),
                    answers=InMemoryAnswerRepository(_completed_results(questions)),
                    store=store,
                    clock=FixedClock(),
                )
            )

            # When: the terminal job is projected into the dashboard snapshot.
            refreshed = materializer.materialize_if_terminal(REFRESH_JOB_ID)

            # Then: structured answers replace values and failures remain NA.
            self.assertIsNotNone(refreshed)
            self.assertNotEqual(refreshed.snapshot.snapshot_id, base.snapshot.snapshot_id)
            self.assertEqual(
                refreshed.metrics[MetricId.REVENUE].observations[1].normalized_value,
                Decimal("150"),
            )
            failed = refreshed.metrics[MetricId.OPERATING_INCOME].observations[1]
            self.assertEqual(failed.status, MetricStatus.MISSING)
            self.assertIsNone(failed.normalized_value)
            derived = refreshed.metrics[MetricId.OPERATING_MARGIN].observations[1]
            self.assertEqual(derived.status, MetricStatus.MISSING)
            self.assertEqual(store.get_current(request().company_id), refreshed)
            completed_job = store.get_job(REFRESH_JOB_ID)
            self.assertIsNotNone(completed_job)
            assert completed_job is not None
            self.assertEqual(completed_job.status, MaterializationStatus.READY)
            self.assertEqual(completed_job.completed_requests, len(questions))
            self.assertEqual(
                completed_job.published_snapshot_id,
                refreshed.snapshot.snapshot_id,
            )

    def test_nonterminal_job_keeps_current_snapshot(self) -> None:
        # Given: at least one question is still queued.
        questions = list(_terminal_questions())
        questions[0] = questions[0].model_copy(
            update={
                "status": BiQuestionStatus.QUEUED,
                "workflow_run_id": None,
                "attempt_count": 0,
                "started_at": None,
                "completed_at": None,
            }
        )
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            base = _base_snapshot()
            store.publish(base)
            materializer = BiQuestionSnapshotMaterializer(
                BiQuestionSnapshotMaterializerServices(
                    questions=InMemoryQuestionService(tuple(questions)),
                    answers=InMemoryAnswerRepository(()),
                    store=store,
                    clock=FixedClock(),
                )
            )

            # When: materialization is checked before the job is terminal.
            refreshed = materializer.materialize_if_terminal(REFRESH_JOB_ID)

            # Then: no partial in-flight snapshot replaces the current dashboard.
            self.assertIsNone(refreshed)
            self.assertEqual(store.get_current(request().company_id), base)

    def test_publishing_service_checks_job_after_answer_commit(self) -> None:
        # Given: an answer write completes through the worker service decorator.
        saved = _terminal_questions()[0]
        materializer = RecordingMaterializer()
        service = BiPublishingQuestionService(
            RecordingQuestionService(saved),
            materializer,
        )

        # When: the worker saves its answer.
        result = service.save_answer(object())

        # Then: snapshot publication is checked for that exact job.
        self.assertEqual(result, saved)
        self.assertEqual(materializer.job_ids, [saved.materialization_job_id])


if __name__ == "__main__":
    unittest.main()
