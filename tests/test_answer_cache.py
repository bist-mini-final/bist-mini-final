from backend.storage.answer_cache import AnswerCacheRepository


def test_answer_cache_in_memory() -> None:
    repository = AnswerCacheRepository()
    repository.save_cached_answer("question-1", "one?", "answer one")
    repository.save_cached_answer("question-2", "two?", "answer two")

    assert repository.get_cached_answer("question-1") == "answer one"
    assert repository.get_cached_answer("question-2") == "answer two"
    assert repository.get_cached_answer("question-3") is None
    assert len(repository.question_candidates()) == 2

    assert repository.clear_cached_answers() == 2
    assert repository.get_cached_answer("question-1") is None

