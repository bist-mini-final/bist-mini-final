from datetime import UTC, datetime
import unittest

from backend.bi.materialization_models import BiDocumentProfile, BiProfilingFailure
from backend.bi.profile_repository import PersistedBiDocumentProfiler
from backend.bi.tests.test_materializer import profile, request


class RecordingProfiler:
    def __init__(self, results) -> None:
        self._results = iter(results)
        self.calls = 0

    def profile(self, materialization):
        del materialization
        self.calls += 1
        return next(self._results)


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.stored: BiDocumentProfile | None = None
        self.saved_at: datetime | None = None

    def get(self, materialization):
        del materialization
        return self.stored

    def save(self, materialization, document_profile, saved_at):
        del materialization
        if self.stored is None:
            self.stored = document_profile
            self.saved_at = saved_at
        return self.stored


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 21, tzinfo=UTC)


class PersistedBiDocumentProfilerTests(unittest.TestCase):
    def test_first_valid_profile_is_saved_and_reused_without_second_llm_call(self) -> None:
        # Given: a valid first profile and a different result that must never be used.
        delegate = RecordingProfiler(
            [
                profile(),
                profile().model_copy(update={"periods": profile().periods[:1]}),
            ]
        )
        repository = InMemoryProfileRepository()
        profiler = PersistedBiDocumentProfiler(delegate, repository, FixedClock())

        # When
        first = profiler.profile(request())
        second = profiler.profile(request())

        # Then
        self.assertEqual(first, profile())
        self.assertEqual(second, profile())
        self.assertEqual(delegate.calls, 1)
        self.assertEqual(repository.stored, profile())

    def test_failed_profile_is_not_saved_and_next_attempt_can_retry(self) -> None:
        # Given
        failure = BiProfilingFailure("context_cells_missing", "no context")
        delegate = RecordingProfiler([failure, profile()])
        repository = InMemoryProfileRepository()
        profiler = PersistedBiDocumentProfiler(delegate, repository, FixedClock())

        # When / Then
        self.assertEqual(profiler.profile(request()), failure)
        self.assertIsNone(repository.stored)
        self.assertEqual(profiler.profile(request()), profile())
        self.assertEqual(delegate.calls, 2)


if __name__ == "__main__":
    unittest.main()
