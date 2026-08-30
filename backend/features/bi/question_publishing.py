import logging
from datetime import datetime
from typing import Protocol

from pydantic import ValidationError

from backend.domains.bi.domain.models import (
    BiDashboardSnapshot,
    BiMaterializationJob,
    JobId,
    MaterializationStatus,
)
from backend.domains.bi.domain.question_records import (
    BiAnswerRecord,
    BiQuestionClaim,
    BiQuestionJobProgress,
    BiQuestionRecord,
    QuestionId,
    WorkflowRunId,
)

from .postgres_store import BiPostgresStoreError
from .profile_repository import BiDocumentProfileRepositoryError
from .question_repository import BiQuestionRepositoryError
from .question_snapshot import BiQuestionSnapshotDataError
from .question_snapshot_repository import BiQuestionSnapshotRepositoryError

logger = logging.getLogger(__name__)

BiQuestionPublicationError = (
    BiPostgresStoreError
    | BiDocumentProfileRepositoryError
    | BiQuestionRepositoryError
    | BiQuestionSnapshotDataError
    | BiQuestionSnapshotRepositoryError
    | ValidationError
)

_PUBLICATION_FAILURE_TYPES = (
    BiPostgresStoreError,
    BiDocumentProfileRepositoryError,
    BiQuestionRepositoryError,
    BiQuestionSnapshotDataError,
    BiQuestionSnapshotRepositoryError,
    ValidationError,
)


class BiQuestionSnapshotMaterializerPort(Protocol):
    def materialize_if_terminal(
        self,
        job_id: JobId,
    ) -> BiDashboardSnapshot | None: ...


class BiQuestionWorkerServicePort(Protocol):
    def claim_next(self, command: BiQuestionClaim) -> BiQuestionRecord | None: ...

    def claim_next_batch(
        self,
        command: BiQuestionClaim,
        batch_size: int,
    ) -> tuple[BiQuestionRecord, ...]: ...

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord: ...

    def heartbeat(
        self,
        question_id: QuestionId,
        workflow_run_id: WorkflowRunId,
    ) -> bool: ...


class BiQuestionPublicationStatePort(Protocol):
    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None: ...

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]: ...


class BiQuestionPublicationStorePort(Protocol):
    def get_job(self, job_id: JobId) -> BiMaterializationJob | None: ...

    def save_job(self, job: BiMaterializationJob) -> None: ...


class BiQuestionPublicationClockPort(Protocol):
    def now(self) -> datetime: ...


class BiQuestionPublicationFailureReporterPort(Protocol):
    def mark_failed(
        self,
        job_id: JobId,
        error: BiQuestionPublicationError,
    ) -> None: ...


class BiQuestionPublicationFailureReporter:
    def __init__(
        self,
        questions: BiQuestionPublicationStatePort,
        store: BiQuestionPublicationStorePort,
        clock: BiQuestionPublicationClockPort,
    ) -> None:
        self._questions = questions
        self._store = store
        self._clock = clock

    def mark_failed(
        self,
        job_id: JobId,
        error: BiQuestionPublicationError,
    ) -> None:
        progress = self._questions.get_job_progress(job_id)
        questions = self._questions.list_questions(job_id)
        if progress is None or not questions:
            return
        now = self._clock.now()
        existing = self._store.get_job(job_id)
        first = questions[0]
        job = existing or BiMaterializationJob(
            job_id=job_id,
            company_id=first.company_id,
            workbook_hash=first.workbook_hash,
            status=MaterializationStatus.FAILED,
            completed_requests=0,
            total_requests=progress.total_questions,
            started_at=min(question.created_at for question in questions),
            updated_at=now,
        )
        self._store.save_job(
            job.model_copy(
                update={
                    "status": MaterializationStatus.FAILED,
                    "completed_requests": (
                        progress.completed_questions + progress.failed_questions
                    ),
                    "total_requests": progress.total_questions,
                    "error_code": "question_snapshot_publication_failed",
                    "message": str(error)[:500],
                    "updated_at": now,
                }
            )
        )


class BiPublishingQuestionService:
    def __init__(
        self,
        service: BiQuestionWorkerServicePort,
        materializer: BiQuestionSnapshotMaterializerPort,
        failure_reporter: BiQuestionPublicationFailureReporterPort,
    ) -> None:
        self._service = service
        self._materializer = materializer
        self._failure_reporter = failure_reporter

    def claim_next(self, command: BiQuestionClaim) -> BiQuestionRecord | None:
        return self._service.claim_next(command)

    def claim_next_batch(
        self,
        command: BiQuestionClaim,
        batch_size: int,
    ) -> tuple[BiQuestionRecord, ...]:
        return self._service.claim_next_batch(command, batch_size=batch_size)

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord:
        saved = self._service.save_answer(answer)
        try:
            self._materializer.materialize_if_terminal(saved.materialization_job_id)
        except _PUBLICATION_FAILURE_TYPES as error:
            logger.exception(
                "BI question snapshot publication failed",
                extra={"job_id": str(saved.materialization_job_id)},
            )
            self._failure_reporter.mark_failed(
                saved.materialization_job_id,
                error,
            )
        return saved

    def heartbeat(
        self,
        question_id: QuestionId,
        workflow_run_id: WorkflowRunId,
    ) -> bool:
        return self._service.heartbeat(question_id, workflow_run_id)
