from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.bi.initial_snapshot import (
    BiInitialSnapshotMaterializer,
    BiInitialSnapshotServices,
    BiPersistedAnswerBatch,
)
from backend.bi.models import BiCompany, MetricId, MetricStatus
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.test_materializer import request
from backend.bi.tests.test_materializer import profile
from backend.bi.tests.test_question_snapshot_materializer import (
    FixedClock,
    _completed_results,
    _terminal_questions,
)


class InMemoryBootstrapRepository:
    def __init__(self, batch: BiPersistedAnswerBatch) -> None:
        self._batch = batch

    def latest_batch(self, company_id, workbook_hash):
        del company_id, workbook_hash
        return self._batch


class FixedSourceResolver:
    def resolve(self, question):
        del question
        return request().source


class InMemoryProfileRepository:
    def get(self, materialization):
        self.materialization = materialization
        return profile()


class BiInitialSnapshotMaterializerTests(unittest.TestCase):
    def test_persisted_answers_build_first_snapshot_with_missing_values_as_na(self) -> None:
        # Given: completed PostgreSQL answers exist before any file snapshot.
        questions = _terminal_questions()
        batch = BiPersistedAnswerBatch(
            questions=questions,
            results=_completed_results(questions),
        )
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            materializer = BiInitialSnapshotMaterializer(
                BiInitialSnapshotServices(
                    answers=InMemoryBootstrapRepository(batch),
                    source_resolver=FixedSourceResolver(),
                    profiles=InMemoryProfileRepository(),
                    store=store,
                    clock=FixedClock(),
                )
            )

            # When: the company dashboard is requested for the first time.
            initial = materializer.materialize(
                BiCompany(
                    company_id=request().company_id,
                    display_name=request().display_name,
                ),
                request().source.workbook_hash,
            )

            # Then: stored results are published and the failed metric remains NA.
            self.assertIsNotNone(initial)
            self.assertEqual(store.get_current(request().company_id), initial)
            self.assertEqual(initial.periods, profile().periods)
            failed = initial.metrics[MetricId.OPERATING_INCOME].observations[1]
            self.assertEqual(failed.status, MetricStatus.MISSING)
            self.assertIsNone(failed.normalized_value)


if __name__ == "__main__":
    unittest.main()
