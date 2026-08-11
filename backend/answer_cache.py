import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple


class AnswerCacheRepository:
    """Persists user questions and final answers used by Query Input cache lookup."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self._lock = Lock()
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
        self._questions[question_id] = {
            "id": question_id,
            "question": question_text,
        }
        self._answers[question_id] = answer
        self._persist()

    def clear_cached_answers(self) -> int:
        removed = len(self._answers)
        self._questions.clear()
        self._answers.clear()
        if self.path is not None:
            with self._lock:
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
        temporary_path = self.path.with_suffix(".json.tmp")
        document = {
            "questions": self._questions,
            "answers": {
                question_id: {"luna_reader_answer": answer}
                for question_id, answer in self._answers.items()
            },
        }
        with self._lock:
            temporary_path.write_text(
                json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
