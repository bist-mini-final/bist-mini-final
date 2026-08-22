"""Zero-I/O in-memory repository for question and answer pairs."""

from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple


class AnswerCacheRepository:
    """In-memory cache for user questions and final answers."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self._lock = RLock()
        self._questions: Dict[str, Dict[str, Any]] = {}
        self._answers: Dict[str, str] = {}

    def get_cached_answer(self, question_id: str) -> Optional[str]:
        with self._lock:
            return self._answers.get(question_id)

    def save_cached_answer(
        self,
        question_id: str,
        question_text: str,
        answer: str,
    ) -> None:
        with self._lock:
            self._questions[question_id] = {
                "id": question_id,
                "question": question_text,
            }
            self._answers[question_id] = answer

    def clear_cached_answers(self) -> int:
        with self._lock:
            removed = len(self._answers)
            self._questions.clear()
            self._answers.clear()
            return removed

    def question_candidates(self) -> List[Tuple[str, str]]:
        with self._lock:
            return [
                (question_id, self._questions[question_id]["question"])
                for question_id in self._answers
                if question_id in self._questions
            ]
