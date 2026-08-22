from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.bi.extraction_models import (
    BiMetricExtractionRequest,
    BiMetricExtractionResult,
)
from backend.bi.materializer import BiMaterializer, BiMaterializerServices
from backend.bi.models import JobId, MaterializationStatus
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.test_materializer import FixedClock, FakeProfiler, profile, request
from backend.llm.chat_completion import ChatCompletionError


class FailingExtractor:
    def extract(
        self,
        request: BiMetricExtractionRequest,
    ) -> BiMetricExtractionResult:
        del request
        raise ChatCompletionError("structured completion failed")


class BiMaterializerFailureTests(unittest.TestCase):
    def test_extraction_failure_is_persisted_as_failed_job(self) -> None:
        # Given: metric extraction raises a known pipeline failure.
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            materializer = BiMaterializer(
                BiMaterializerServices(
                    profiler=FakeProfiler(profile()),
                    extractor=FailingExtractor(),
                    store=store,
                    clock=FixedClock(),
                )
            )

            # When: the background materialization reaches extraction.
            outcome = materializer.materialize(request(), JobId("job-extraction-failed"))

            # Then: polling observes a terminal failure instead of extracting forever.
            self.assertEqual(outcome.job.status, MaterializationStatus.FAILED)
            self.assertEqual(outcome.job.error_code, "chat_completion_failed")
            self.assertEqual(outcome.job.completed_requests, 0)
            self.assertIsNone(outcome.snapshot)
            self.assertEqual(store.get_job(outcome.job.job_id), outcome.job)


if __name__ == "__main__":
    unittest.main()
