from datetime import UTC, datetime

from backend.features.bi.models import (
    BiMaterializationJob,
    CompanyId,
    IndexId,
    JobId,
    MaterializationStatus,
    MetricId,
    PeriodId,
)
from backend.features.bi.postgres_store import BiPostgresStoreError
from backend.features.bi.question_publishing import (
    BiPublishingQuestionService,
    BiQuestionPublicationError,
    BiQuestionPublicationFailureReporter,
)
from backend.features.bi.question_records import (
    AnswerId,
    BiAnswerOutcome,
    BiAnswerRecord,
    BiFailedAnswerRecord,
    BiQuestionClaim,
    BiQuestionJobProgress,
    BiQuestionRecord,
    BiQuestionStatus,
    QuestionId,
    QuestionVersion,
    WorkflowRunId,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def completed_question() -> BiQuestionRecord:
    return BiQuestionRecord(
        question_id=QuestionId("question-test"),
        materialization_job_id=JobId("question-reset-test"),
        company_id=CompanyId("company-test"),
        workbook_hash="a" * 64,
        index_id=IndexId("index-test"),
        metric_id=MetricId.REVENUE,
        period_id=PeriodId("fy-2025-12-31"),
        question_version=QuestionVersion("2"),
        question_text="question",
        status=BiQuestionStatus.COMPLETED,
        workflow_run_id=WorkflowRunId("worker-test"),
        attempt_count=1,
        created_at=NOW,
        updated_at=NOW,
        started_at=NOW,
        completed_at=NOW,
    )


class AnswerService:
    def __init__(self, question: BiQuestionRecord) -> None:
        self._question = question

    def claim_next(self, command: BiQuestionClaim) -> BiQuestionRecord | None:
        return None

    def claim_next_batch(
        self,
        command: BiQuestionClaim,
        batch_size: int,
    ) -> tuple[BiQuestionRecord, ...]:
        return ()

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord:
        return self._question

    def heartbeat(
        self,
        question_id: QuestionId,
        workflow_run_id: WorkflowRunId,
    ) -> bool:
        return True


class FailingMaterializer:
    def materialize_if_terminal(self, job_id: JobId) -> None:
        raise BiPostgresStoreError("get_current", "invalid metric contract")


class FailureReporter:
    def __init__(self) -> None:
        self.failure: tuple[JobId, BiQuestionPublicationError] | None = None

    def mark_failed(
        self,
        job_id: JobId,
        error: BiQuestionPublicationError,
    ) -> None:
        self.failure = (job_id, error)


class QuestionState:
    def __init__(self, question: BiQuestionRecord) -> None:
        self._question = question

    def get_job_progress(self, job_id: JobId) -> BiQuestionJobProgress:
        return BiQuestionJobProgress(
            job_id=job_id,
            total_questions=1,
            queued_questions=0,
            running_questions=0,
            completed_questions=1,
            failed_questions=0,
        )

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]:
        return (self._question,)


class JobStore:
    def __init__(self) -> None:
        self.saved: BiMaterializationJob | None = None

    def get_job(self, job_id: JobId) -> BiMaterializationJob | None:
        return None

    def save_job(self, job: BiMaterializationJob) -> None:
        self.saved = job


class FixedClock:
    def now(self) -> datetime:
        return NOW


def test_keeps_saved_answer_and_reports_snapshot_publication_failure() -> None:
    question = completed_question()
    reporter = FailureReporter()
    service = BiPublishingQuestionService(
        AnswerService(question),
        FailingMaterializer(),
        reporter,
    )
    answer = BiFailedAnswerRecord(
        answer_id=AnswerId("answer-test"),
        question_id=question.question_id,
        workflow_run_id=WorkflowRunId("worker-test"),
        outcome=BiAnswerOutcome.FAILED,
        error_code="pipeline_failure",
        error_message="failed",
        latency_ms=1,
        created_at=NOW,
        updated_at=NOW,
    )

    saved = service.save_answer(answer)

    assert saved is question
    assert reporter.failure is not None
    assert reporter.failure[0] == question.materialization_job_id


def test_marks_materialization_job_failed_when_snapshot_publication_fails() -> None:
    question = completed_question()
    store = JobStore()
    reporter = BiQuestionPublicationFailureReporter(
        QuestionState(question),
        store,
        FixedClock(),
    )

    reporter.mark_failed(
        question.materialization_job_id,
        BiPostgresStoreError("get_current", "invalid metric contract"),
    )

    assert store.saved is not None
    assert store.saved.status is MaterializationStatus.FAILED
    assert store.saved.completed_requests == 1
    assert store.saved.error_code == "question_snapshot_publication_failed"
