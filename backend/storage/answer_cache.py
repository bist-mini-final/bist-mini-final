"""JSON-backed repository for cached question and answer pairs."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterator, List, Optional, Tuple
from uuid import uuid4


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Take an advisory lock shared by local worker processes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt
            import time

            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)

            # Retry until lock is acquired instead of raising OSError
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)

            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class AnswerCacheRepository:
    """Persists user questions and final answers used by Query Input cache lookup."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self._lock = RLock()
        self._questions: Dict[str, Dict[str, Any]] = {}
        self._answers: Dict[str, str] = {}
        self._load()

    def get_cached_answer(self, question_id: str) -> Optional[str]:
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
            self._persist()

    def clear_cached_answers(self) -> int:
        with self._lock:
            removed = len(self._answers)
            self._questions.clear()
            self._answers.clear()
            if self.path is not None:
                with _exclusive_file_lock(self.path.with_suffix(".lock")):
                    self.path.unlink(missing_ok=True)
            return removed

    def question_candidates(self) -> List[Tuple[str, str]]:
        return [
            (question_id, self._questions[question_id]["question"])
            for question_id in self._answers
            if question_id in self._questions
        ]

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"답변 캐시를 읽을 수 없습니다: {self.path}") from error
        if not isinstance(document, dict):
            raise ValueError("답변 캐시 최상위 값은 객체여야 합니다")
        questions = document.get("questions", {})
        answers = document.get("answers", {})
        if not isinstance(questions, dict) or not isinstance(answers, dict):
            raise ValueError("답변 캐시의 questions와 answers는 객체여야 합니다")
        for question_id, question in questions.items():
            if not isinstance(question_id, str) or not isinstance(question, dict):
                raise ValueError("답변 캐시 question 항목 형식이 올바르지 않습니다")
            question_text = question.get("question")
            if not isinstance(question_text, str) or not question_text.strip():
                raise ValueError("답변 캐시에 빈 질문이 있습니다")
            self._questions[question_id] = {
                "id": question_id,
                "question": question_text,
            }
        for question_id, answer_value in answers.items():
            if isinstance(answer_value, str):
                answer = answer_value
            elif isinstance(answer_value, dict):
                answer = answer_value.get("luna_reader_answer")
            else:
                answer = None
            if not isinstance(question_id, str) or not isinstance(answer, str):
                raise ValueError("답변 캐시 answer 항목 형식이 올바르지 않습니다")
            if question_id not in self._questions:
                raise ValueError(f"답변 {question_id}에 대응하는 질문이 없습니다")
            self._answers[question_id] = answer

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with _exclusive_file_lock(self.path.with_suffix(".lock")):
                disk_questions: Dict[str, Dict[str, Any]] = {}
                disk_answers: Dict[str, str] = {}
                if self.path.is_file():
                    try:
                        stored = json.loads(self.path.read_text(encoding="utf-8"))
                        if not isinstance(stored, dict):
                            raise ValueError("답변 캐시 최상위 값은 객체여야 합니다")
                        raw_questions = stored.get("questions", {})
                        raw_answers = stored.get("answers", {})
                        if isinstance(raw_questions, dict):
                            disk_questions.update(raw_questions)
                        if isinstance(raw_answers, dict):
                            for question_id, answer_value in raw_answers.items():
                                if isinstance(answer_value, str):
                                    disk_answers[question_id] = answer_value
                                elif isinstance(answer_value, dict) and isinstance(
                                    answer_value.get("luna_reader_answer"), str
                                ):
                                    disk_answers[question_id] = answer_value[
                                        "luna_reader_answer"
                                    ]
                    except (json.JSONDecodeError, UnicodeError) as error:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(
                            "답변 캐시 파일 손상으로 디스크 상태를 무시합니다: %s",
                            error,
                        )

                disk_questions.update(self._questions)
                disk_answers.update(self._answers)
                self._questions = disk_questions
                self._answers = disk_answers
                document = {
                    "questions": self._questions,
                    "answers": {
                        question_id: {"luna_reader_answer": answer}
                        for question_id, answer in self._answers.items()
                    },
                }
                temporary_path = self.path.with_name(
                    f"{self.path.name}.{uuid4().hex}.tmp"
                )
                try:
                    temporary_path.write_text(
                        json.dumps(
                            document,
                            ensure_ascii=False,
                            sort_keys=True,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    temporary_path.replace(self.path)
                finally:
                    temporary_path.unlink(missing_ok=True)
