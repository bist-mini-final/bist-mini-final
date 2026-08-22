from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.bi.catalog import METRIC_CATALOG, SourceMetricDefinition
from backend.bi.models import JobId, MaterializationStatus, MetricStatus
from backend.bi.queued_materializer import (
    BiQueuedMaterializer,
    BiQueuedMaterializerServices,
)
from backend.bi.question_batch import build_question_batch
from backend.bi.question_service import summarize_questions
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.test_materializer import profile, request


NOW = datetime(2026, 8, 22, tzinfo=UTC)


class FixedProfiler:
    def profile(self, materialization):
        del materialization
        return profile()


class RecordingQuestions:
    def __init__(self) -> None:
        self.plan = None
        self.questions = ()

    def queue_materialization_questions(self, plan):
        self.plan = plan
        self.questions = build_question_batch(plan).questions
        return summarize_questions(plan.job_id, self.questions)


class AdvancingClock:
    def __init__(self) -> None:
        self.calls = 0

    def now(self):
        value = NOW + timedelta(seconds=self.calls)
        self.calls += 1
        return value


class BiQueuedMaterializerTests(unittest.TestCase):
    def test_index_completion_profiles_then_queues_single_metric_questions(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            questions = RecordingQuestions()
            runner = BiQueuedMaterializer(
                BiQueuedMaterializerServices(
                    profiler=FixedProfiler(),
                    questions=questions,
                    store=store,
                    clock=AdvancingClock(),
                )
            )

            outcome = runner.materialize(request(), JobId("job-queued-upload"))

            self.assertEqual(outcome.job.status, MaterializationStatus.EXTRACTING)
            self.assertEqual(outcome.job.total_requests, len(questions.questions))
            self.assertEqual(len(questions.questions), 26)
            self.assertTrue(
                all("값을 찾아라" in item.question_text for item in questions.questions)
            )
            snapshot = store.get_current(request().company_id)
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertTrue(
                all(
                    observation.status is MetricStatus.MISSING
                    for metric_id, series in snapshot.metrics.items()
                    if isinstance(METRIC_CATALOG[metric_id], SourceMetricDefinition)
                    for observation in series.observations
                )
            )


if __name__ == "__main__":
    unittest.main()
