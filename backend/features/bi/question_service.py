from collections import Counter
from typing import Protocol

from .question_batch import BiQuestionBatchPlan, build_question_batch
from .question_records import (
    BiAnswerRecord,
    BiCompletedAnswerRecord,
    BiLatestAnswerQuery,
    BiQuestionBatch,
    BiQuestionClaim,
    BiQuestionJobProgress,
    BiQuestionRecord,
    BiQuestionStart,
    BiQuestionStatus,
    JobId,
    QuestionId,
)


def summarize_questions(
    job_id: JobId,
    questions: tuple[BiQuestionRecord, ...],
) -> BiQuestionJobProgress:
    counts = Counter(question.status for question in questions)
    return BiQuestionJobProgress(
        job_id=job_id,
        total_questions=len(questions),
        queued_questions=counts[BiQuestionStatus.QUEUED],
        running_questions=counts[BiQuestionStatus.RUNNING],
        completed_questions=counts[BiQuestionStatus.COMPLETED],
        failed_questions=counts[BiQuestionStatus.FAILED],
    )


class BiQuestionRepositoryPort(Protocol):
    def register_questions(
        self,
        questions: tuple[BiQuestionRecord, ...],
    ) -> tuple[BiQuestionRecord, ...]: ...

    def get_question(self, question_id: QuestionId) -> BiQuestionRecord | None: ...

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]: ...

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None: ...

    def claim_next(
        self,
        command: BiQuestionClaim,
    ) -> BiQuestionRecord | None: ...

    def start_question(self, command: BiQuestionStart) -> BiQuestionRecord: ...

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord: ...

    def latest_answers(
        self,
        query: BiLatestAnswerQuery,
    ) -> tuple[BiCompletedAnswerRecord, ...]: ...


class BiQuestionService:
    def __init__(self, repository: BiQuestionRepositoryPort) -> None:
        self._repository = repository

    def register_questions(
        self,
        batch: BiQuestionBatch,
    ) -> tuple[BiQuestionRecord, ...]:
        return self._repository.register_questions(batch.questions)

    def register_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> tuple[BiQuestionRecord, ...]:
        return self.register_questions(build_question_batch(plan))

    def queue_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> BiQuestionJobProgress:
        questions = self.register_materialization_questions(plan)
        return summarize_questions(plan.job_id, questions)

    def get_question(self, question_id: QuestionId) -> BiQuestionRecord | None:
        return self._repository.get_question(question_id)

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]:
        return self._repository.list_questions(job_id)

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None:
        return self._repository.get_job_progress(job_id)

    def claim_next(
        self,
        command: BiQuestionClaim,
    ) -> BiQuestionRecord | None:
        return self._repository.claim_next(command)

    def start_question(self, command: BiQuestionStart) -> BiQuestionRecord:
        return self._repository.start_question(command)

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord:
        return self._repository.save_answer(answer)

    def latest_answers(
        self,
        query: BiLatestAnswerQuery,
    ) -> tuple[BiCompletedAnswerRecord, ...]:
        return self._repository.latest_answers(query)
