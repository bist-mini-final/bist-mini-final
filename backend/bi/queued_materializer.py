from dataclasses import dataclass
from typing import Protocol, assert_never

from backend.llm.chat_completion import ChatCompletionError
from backend.modules.base import ModuleExecutionError
from pydantic import ValidationError

from .catalog import METRIC_CATALOG, SourceMetricDefinition
from .extraction_models import BiMetricExtractionResult
from .materialization_models import (
    BiDocumentProfile,
    BiMaterializationOutcome,
    BiProfilingFailure,
    BiProfilingResult,
    BiSnapshotBuildInput,
)
from .materializer import BiDocumentProfilerPort, ClockPort
from .models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    JobId,
    MaterializationStatus,
    MetricStatus,
    UnavailableObservation,
)
from .profile_repository import BiDocumentProfileRepositoryError
from .question_batch import BiQuestionBatchPlan
from .question_records import BiQuestionJobProgress
from .question_repository import BiQuestionRegistrationError
from .question_repository_queries import BiQuestionRepositoryError
from .rag_adapter import RagPipelineContractError
from .snapshot_builder import BiSnapshotBuilder


class BiQueuedQuestionPort(Protocol):
    def queue_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> BiQuestionJobProgress: ...


class BiQueuedSnapshotStorePort(Protocol):
    def register_company(self, company: BiCompany) -> None: ...

    def save_job(self, job: BiMaterializationJob) -> None: ...

    def publish(self, snapshot: BiDashboardSnapshot) -> None: ...


@dataclass(frozen=True, slots=True)
class BiQueuedMaterializerServices:
    profiler: BiDocumentProfilerPort
    questions: BiQueuedQuestionPort
    store: BiQueuedSnapshotStorePort
    clock: ClockPort


class BiQueuedMaterializer:
    def __init__(self, services: BiQueuedMaterializerServices) -> None:
        self._services = services

    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome:
        started_at = self._services.clock.now()
        job = BiMaterializationJob(
            job_id=job_id,
            company_id=request.company_id,
            workbook_hash=request.source.workbook_hash,
            status=MaterializationStatus.PROFILING,
            completed_requests=0,
            total_requests=0,
            started_at=started_at,
            updated_at=started_at,
        )
        self._services.store.register_company(
            BiCompany(
                company_id=request.company_id,
                display_name=request.display_name,
            )
        )
        self._services.store.save_job(job)
        try:
            profile_result = self._services.profiler.profile(request)
        except (
            ChatCompletionError,
            ModuleExecutionError,
            ValidationError,
            RagPipelineContractError,
            BiDocumentProfileRepositoryError,
        ) as error:
            return self._failed(job, error)
        match profile_result:
            case BiProfilingFailure(code=code, message=message):
                return self._profile_failed(job, code, message)
            case BiDocumentProfile() as profile:
                pass
            case unreachable:
                assert_never(unreachable)

        pending = self._pending_results(profile)
        extracting = job.model_copy(
            update={
                "status": MaterializationStatus.EXTRACTING,
                "total_requests": len(pending),
                "updated_at": self._services.clock.now(),
                "message": "지표 질문을 병렬 처리 대기열에 등록합니다.",
            }
        )
        self._services.store.save_job(extracting)
        snapshot = BiSnapshotBuilder().build(
            BiSnapshotBuildInput(
                request=request,
                job_id=job_id,
                profile=profile,
                extracted=pending,
                generated_at=self._services.clock.now(),
            )
        )
        self._services.store.publish(snapshot)
        try:
            progress = self._services.questions.queue_materialization_questions(
                BiQuestionBatchPlan(
                    materialization=request,
                    periods=profile.periods,
                    job_id=job_id,
                    created_at=self._services.clock.now(),
                )
            )
        except (BiQuestionRepositoryError, BiQuestionRegistrationError) as error:
            return self._failed(extracting, error, snapshot)
        queued = extracting.model_copy(
            update={
                "total_requests": progress.total_questions,
                "updated_at": self._services.clock.now(),
                "message": f"지표 질문 {progress.total_questions}건을 병렬 처리 중입니다.",
            }
        )
        self._services.store.save_job(queued)
        return BiMaterializationOutcome(job=queued, snapshot=snapshot)

    @staticmethod
    def _pending_results(
        profile: BiDocumentProfile,
    ) -> tuple[BiMetricExtractionResult, ...]:
        return tuple(
            BiMetricExtractionResult(
                metric_id=metric_id,
                period_id=period.period_id,
                value_kind=definition.value_kind,
                currency=None,
                scale=None,
                observation=UnavailableObservation(
                    period_id=period.period_id,
                    status=MetricStatus.MISSING,
                    reason="answer_pending",
                ),
            )
            for metric_id, definition in METRIC_CATALOG.items()
            if isinstance(definition, SourceMetricDefinition)
            for period in profile.periods
        )

    def _profile_failed(
        self,
        job: BiMaterializationJob,
        code: str,
        message: str,
    ) -> BiMaterializationOutcome:
        failed = job.model_copy(
            update={
                "status": MaterializationStatus.FAILED,
                "error_code": code,
                "message": message,
                "updated_at": self._services.clock.now(),
            }
        )
        self._services.store.save_job(failed)
        return BiMaterializationOutcome(job=failed, snapshot=None)

    def _failed(
        self,
        job: BiMaterializationJob,
        error: Exception,
        snapshot: BiDashboardSnapshot | None = None,
    ) -> BiMaterializationOutcome:
        if isinstance(error, RagPipelineContractError):
            code = error.code
        elif isinstance(error, ChatCompletionError):
            code = "chat_completion_failed"
        elif isinstance(error, ModuleExecutionError):
            code = "pipeline_module_failed"
        elif isinstance(error, ValidationError):
            code = "pipeline_contract_invalid"
        elif isinstance(error, BiDocumentProfileRepositoryError):
            code = "profile_repository_failed"
        elif isinstance(error, BiQuestionRegistrationError):
            code = "question_registration_failed"
        else:
            code = "question_repository_failed"
        failed = job.model_copy(
            update={
                "status": MaterializationStatus.FAILED,
                "error_code": code,
                "message": (str(error).strip() or type(error).__name__)[:500],
                "updated_at": self._services.clock.now(),
            }
        )
        self._services.store.save_job(failed)
        return BiMaterializationOutcome(job=failed, snapshot=snapshot)
