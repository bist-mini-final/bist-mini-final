from pathlib import Path
from tempfile import TemporaryDirectory

from backend.storage.answer_cache import AnswerCacheRepository


def test_answer_cache_merges_writes_from_stale_instances() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "answers.json"
        first_repository = AnswerCacheRepository(path)
        second_repository = AnswerCacheRepository(path)

        first_repository.save_cached_answer("question-1", "one?", "answer one")
        second_repository.save_cached_answer("question-2", "two?", "answer two")

        reloaded = AnswerCacheRepository(path)
        assert reloaded.get_cached_answer("question-1") == "answer one"
        assert reloaded.get_cached_answer("question-2") == "answer two"
