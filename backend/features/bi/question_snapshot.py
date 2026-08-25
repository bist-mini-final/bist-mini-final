from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, assert_never

from .catalog import METRIC_CATALOG, SourceMetricDefinition
from .extraction_models import BiMetricExtractionResult
from .materialization_models import BiDocumentProfile, BiSnapshotRefreshInput
from .models import (
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    CompanyId,
    JobId,
    MaterializationStatus,
    MetricId,
    MetricStatus,
    PeriodId,
    SnapshotStatus,
    UnavailableObservation,
)
from .question_records import (
    BiAnswerRecord,
    BiQuestionClaim,
    BiQuestionJobProgress,
    BiQuestionRecord,
    BiQuestionStatus,
    QuestionId,
    WorkflowRunId,
)
from .snapshot_builder import BiSnapshotBuilder


class BiQuestionSnapshotQuestionPort(Protocol):
    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None: ...

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]: ...


class BiQuestionSnapshotAnswerPort(Protocol):
    def completed_results(
        self,
        job_id: JobId,
    ) -> tuple[BiMetricExtractionResult, ...]: ...


class BiQuestionSnapshotStorePort(Protocol):
    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None: ...

    def publish(self, snapshot: BiDashboardSnapshot) -> None: ...

    def get_job(self, job_id: JobId) -> BiMaterializationJob | None: ...

    def save_job(self, job: BiMaterializationJob) -> None: ...


class BiQuestionSnapshotClockPort(Protocol):
    def now(self) -> datetime: ...


class BiQuestionSnapshotProfilePort(Protocol):
    def get(
        self,
        request: BiMaterializationRequest,
    ) -> BiDocumentProfile | None: """
        Retrieve the document profile associated with a materialization request.
        
        Parameters:
        	request (BiMaterializationRequest): Request identifying the company and source document.
        
        Returns:
        	BiDocumentProfile | None: The matching document profile, or `None` when unavailable.
        """
        ...


class BiQuestionSnapshotMaterializerPort(Protocol):
    def materialize_if_terminal(
        self,
        job_id: JobId,
    ) -> BiDashboardSnapshot | None: """
        Materialize and publish a dashboard snapshot when a materialization job is terminal.
        
        Parameters:
            job_id (JobId): Identifier of the materialization job.
        
        Returns:
            BiDashboardSnapshot | None: The published snapshot, or `None` when the job is unavailable, still in progress, or the current snapshot cannot be retrieved.
        
        Raises:
            BiQuestionSnapshotDataError: If terminal-job questions are missing, have inconsistent lineage, or lack required completed answers.
        """
        ...


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


@dataclass(frozen=True, slots=True)
class BiQuestionSnapshotDataError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"BI question snapshot data is invalid: {self.reason}"


@dataclass(frozen=True, slots=True)
class BiQuestionSnapshotMaterializerServices:
    questions: BiQuestionSnapshotQuestionPort
    answers: BiQuestionSnapshotAnswerPort
    store: BiQuestionSnapshotStorePort
    clock: BiQuestionSnapshotClockPort
    profiles: BiQuestionSnapshotProfilePort | None = None


class BiQuestionSnapshotMaterializer:
    def __init__(self, services: BiQuestionSnapshotMaterializerServices) -> None:
        self._services = services

    def materialize_if_terminal(
        self,
        job_id: JobId,
    ) -> BiDashboardSnapshot | None:
        """
        Materialize a terminal question job into a published dashboard snapshot.
        
        Parameters:
        	job_id (JobId): Identifier of the question job to materialize.
        
        Returns:
        	BiDashboardSnapshot | None: The published snapshot, or `None` when the job is unavailable, still active, or has no current snapshot.
        
        Raises:
        	BiQuestionSnapshotDataError: If a terminal job has no questions or its questions do not match the current snapshot lineage.
        """
        progress = self._services.questions.get_job_progress(job_id)
        if progress is None or progress.queued_questions or progress.running_questions:
            return None

        questions = self._services.questions.list_questions(job_id)
        if not questions:
            raise BiQuestionSnapshotDataError("terminal job has no questions")
        base = self._services.store.get_current(questions[0].company_id)
        if base is None:
            return None
        self._require_matching_lineage(questions, base)
        request = BiMaterializationRequest(
            company_id=base.company.company_id,
            display_name=base.company.display_name,
            source=base.source,
        )
        profile = (
            self._services.profiles.get(request)
            if self._services.profiles is not None
            else None
        )

        completed = {
            (result.metric_id, result.period_id): result
            for result in self._services.answers.completed_results(job_id)
        }
        question_by_identity = {
            (question.metric_id, question.period_id): question
            for question in questions
        }
        extracted = tuple(
            self._result_for(
                metric_id,
                period.period_id,
                question_by_identity.get((metric_id, period.period_id)),
                completed,
            )
            for metric_id, definition in METRIC_CATALOG.items()
            if isinstance(definition, SourceMetricDefinition)
            for period in base.periods
        )
        snapshot = BiSnapshotBuilder().refresh(
            BiSnapshotRefreshInput(
                base_snapshot=base,
                job_id=job_id,
                extracted=extracted,
                generated_at=self._services.clock.now(),
                profile=profile,
            )
        )
        self._services.store.publish(snapshot)
        job = self._services.store.get_job(job_id)
        if job is not None:
            match snapshot.snapshot.status:
                case SnapshotStatus.READY:
                    status = MaterializationStatus.READY
                case SnapshotStatus.PARTIAL:
                    status = MaterializationStatus.PARTIAL
                case unreachable:
                    assert_never(unreachable)
            self._services.store.save_job(
                job.model_copy(
                    update={
                        "status": status,
                        "completed_requests": (
                            progress.completed_questions + progress.failed_questions
                        ),
                        "total_requests": progress.total_questions,
                        "published_snapshot_id": snapshot.snapshot.snapshot_id,
                        "message": None,
                        "updated_at": self._services.clock.now(),
                    }
                )
            )
        return snapshot

    @staticmethod
    def _require_matching_lineage(
        questions: tuple[BiQuestionRecord, ...],
        base: BiDashboardSnapshot,
    ) -> None:
        for question in questions:
            if (
                question.company_id != base.company.company_id
                or question.workbook_hash != base.source.workbook_hash
                or question.index_id != base.source.index_id
            ):
                raise BiQuestionSnapshotDataError(
                    "question lineage does not match current snapshot"
                )

    @staticmethod
    def _result_for(
        metric_id: MetricId,
        period_id: PeriodId,
        question: BiQuestionRecord | None,
        completed: dict[tuple[MetricId, PeriodId], BiMetricExtractionResult],
    ) -> BiMetricExtractionResult:
        definition = METRIC_CATALOG[metric_id]
        result = completed.get((metric_id, period_id))
        if question is not None and question.status is BiQuestionStatus.COMPLETED:
            if result is None or result.observation.period_id != period_id:
                raise BiQuestionSnapshotDataError(
                    "completed question has no matching structured answer"
                )
            return result
        return BiMetricExtractionResult(
            metric_id=metric_id,
            period_id=period_id,
            value_kind=definition.value_kind,
            currency=None,
            scale=None,
            observation=UnavailableObservation(
                period_id=period_id,
                status=MetricStatus.MISSING,
                reason=("answer_failed" if question is not None else "question_missing"),
            ),
        )


class BiPublishingQuestionService:
    def __init__(
        self,
        service: BiQuestionWorkerServicePort,
        materializer: BiQuestionSnapshotMaterializerPort,
    ) -> None:
        self._service = service
        self._materializer = materializer

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
        self._materializer.materialize_if_terminal(saved.materialization_job_id)
        return saved

    def heartbeat(
        self,
        question_id: QuestionId,
        workflow_run_id: WorkflowRunId,
    ) -> bool:
        return self._service.heartbeat(question_id, workflow_run_id)
