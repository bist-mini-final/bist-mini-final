from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Final, Protocol, assert_never

from pydantic import ValidationError

from backend.llm.chat_completion import ChatCompletionError
from backend.modules.base import ModuleExecutionError

from .catalog import METRIC_CATALOG, DerivedMetricDefinition, SourceMetricDefinition
from .extraction_models import BiMetricExtractionRequest, BiMetricExtractionResult
from .materialization_models import (
    BiDocumentProfile,
    BiMaterializationOutcome,
    BiProfilingFailure,
    BiProfilingResult,
    BiSnapshotBuildInput,
)
from .models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    JobId,
    MaterializationStatus,
    SnapshotStatus,
)
from .rag_adapter import RagPipelineContractError
from .snapshot_builder import BiSnapshotBuilder


BI_MATERIALIZATION_EXCEPTIONS: Final = (
    ChatCompletionError,
    ModuleExecutionError,
    ValidationError,
    RagPipelineContractError,
)
BiMaterializationFailure = (
    ChatCompletionError
    | ModuleExecutionError
    | ValidationError
    | RagPipelineContractError
)


class BiDocumentProfilerPort(Protocol):
    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult: ...


class BiMetricExtractorPort(Protocol):
    def extract(self, request: BiMetricExtractionRequest) -> BiMetricExtractionResult: ...


class BiSnapshotWriterPort(Protocol):
    def register_company(self, company: BiCompany) -> None: ...

    def save_job(self, job: BiMaterializationJob) -> None: ...

    def publish(self, snapshot: BiDashboardSnapshot) -> None: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class BiMaterializerServices:
    profiler: BiDocumentProfilerPort
    extractor: BiMetricExtractorPort
    store: BiSnapshotWriterPort
    clock: ClockPort


class BiMaterializer:
    def __init__(self, services: BiMaterializerServices) -> None:
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
            status=MaterializationStatus.QUEUED,
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
        job = job.model_copy(
            update={
                "status": MaterializationStatus.PROFILING,
                "updated_at": self._services.clock.now(),
            }
        )
        self._services.store.save_job(job)

        try:
            profile_result = self._services.profiler.profile(request)
        except BI_MATERIALIZATION_EXCEPTIONS as error:
            return self._failed_outcome(job, error, completed_requests=0)
        match profile_result:
            case BiProfilingFailure(code=code, message=message):
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
            case BiDocumentProfile() as profile:
                pass
            case unreachable:
                assert_never(unreachable)

        source_metric_ids = []
        for metric_id, definition in METRIC_CATALOG.items():
            match definition:
                case SourceMetricDefinition():
                    source_metric_ids.append(metric_id)
                case DerivedMetricDefinition():
                    continue
                case unreachable:
                    assert_never(unreachable)

        total_requests = len(source_metric_ids) * len(profile.periods)
        job = job.model_copy(
            update={
                "status": MaterializationStatus.EXTRACTING,
                "total_requests": total_requests,
                "updated_at": self._services.clock.now(),
            }
        )
        self._services.store.save_job(job)
        extracted: list[BiMetricExtractionResult] = []
        try:
            for metric_id in source_metric_ids:
                for period in profile.periods:
                    identity = f"{job_id}:{metric_id.value}:{period.period_id}"
                    request_id = "request-" + sha256(
                        identity.encode("utf-8")
                    ).hexdigest()[:24]
                    extracted.append(
                        self._services.extractor.extract(
                            BiMetricExtractionRequest(
                                request_id=request_id,
                                metric_id=metric_id,
                                period_id=period.period_id,
                                period_label=period.label,
                                source=request.source,
                            )
                        )
                    )
        except BI_MATERIALIZATION_EXCEPTIONS as error:
            return self._failed_outcome(
                job,
                error,
                completed_requests=len(extracted),
            )

        job = job.model_copy(
            update={
                "status": MaterializationStatus.MATERIALIZING,
                "completed_requests": len(extracted),
                "updated_at": self._services.clock.now(),
            }
        )
        self._services.store.save_job(job)
        snapshot = BiSnapshotBuilder().build(
            BiSnapshotBuildInput(
                request=request,
                job_id=job_id,
                profile=profile,
                extracted=tuple(extracted),
                generated_at=self._services.clock.now(),
            )
        )
        match snapshot.snapshot.status:
            case SnapshotStatus.READY:
                final_status = MaterializationStatus.READY
            case SnapshotStatus.PARTIAL:
                final_status = MaterializationStatus.PARTIAL
            case unreachable:
                assert_never(unreachable)
        self._services.store.publish(snapshot)
        completed = job.model_copy(
            update={
                "status": final_status,
                "published_snapshot_id": snapshot.snapshot.snapshot_id,
                "updated_at": self._services.clock.now(),
            }
        )
        self._services.store.save_job(completed)
        return BiMaterializationOutcome(job=completed, snapshot=snapshot)

    def _failed_outcome(
        self,
        job: BiMaterializationJob,
        error: BiMaterializationFailure,
        completed_requests: int,
    ) -> BiMaterializationOutcome:
        match error:
            case RagPipelineContractError(code=code):
                error_code = code
            case ChatCompletionError():
                error_code = "chat_completion_failed"
            case ModuleExecutionError():
                error_code = "pipeline_module_failed"
            case ValidationError():
                error_code = "pipeline_contract_invalid"
            case unreachable:
                assert_never(unreachable)
        message = str(error).strip() or type(error).__name__
        failed = job.model_copy(
            update={
                "status": MaterializationStatus.FAILED,
                "completed_requests": completed_requests,
                "error_code": error_code,
                "message": message[:500],
                "updated_at": self._services.clock.now(),
            }
        )
        self._services.store.save_job(failed)
        return BiMaterializationOutcome(job=failed, snapshot=None)
