"""BI command/query use cases independent from the HTTP presentation layer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from backend.domains.bi.application.dashboard_recalculation import (
    BiDashboardRecalculationError,
    recalculate_dashboard,
)
from backend.domains.bi.application.dtos import (
    BiCompanyListResponse,
    BiCompanySummary,
    BiMaterializationAccepted,
    BiMaterializationCandidateListResponse,
)
from backend.domains.bi.application.errors import (
    BiDashboardDeleteActiveError,
    BiPostgresStoreError,
    BiQuestionRegistrationError,
    BiQuestionRepositoryError,
    BiQuestionResetActiveError,
)
from backend.domains.bi.application.projections import (
    accepted,
    build_company_summary,
    build_materialization_candidate,
    is_active,
    job_id_for,
    with_refresh_state,
)
from backend.domains.bi.domain.models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    CompanyId,
    JobId,
    MaterializationStatus,
)
from backend.domains.bi.domain.question_batch import BiQuestionBatchPlan
from backend.domains.bi.domain.question_records import BiQuestionJobProgress
from backend.shared.domain import (
    ApplicationConflict,
    ResourceNotFoundError,
    RetryableInfrastructureError,
)

from .services import BiApiServices

COMPANY_NOT_FOUND: Final = "company not found"
DASHBOARD_NOT_AVAILABLE: Final = "company dashboard is not available"
JOB_NOT_FOUND: Final = "materialization job not found"
MATERIALIZATION_ACTIVE: Final = "company materialization is active"
QUESTION_JOB_NOT_FOUND: Final = "question job not found"
REFRESH_PERIODS_UNAVAILABLE: Final = "dashboard periods are unavailable"


class BiNotFoundError(ResourceNotFoundError):
    code = "HTTP_404"


class BiConflictError(ApplicationConflict):
    code = "HTTP_409"


class BiQueueUnavailableError(RetryableInfrastructureError):
    code = "HTTP_503"


@dataclass(frozen=True, slots=True)
class BiDashboardResult:
    """Application result whose HTTP representation may be ready or pending."""

    snapshot: BiDashboardSnapshot | None = None
    pending_job: BiMaterializationJob | None = None


class BiApplicationService:
    """Coordinate BI queries and commands behind one presentation-neutral API."""

    def __init__(self, services: BiApiServices) -> None:
        self._services = services

    async def list_companies(self) -> BiCompanyListResponse:
        entries = await self._services.store.list_companies_async()
        if not entries:
            return BiCompanyListResponse(companies=())
        company_ids = tuple(entry.company.company_id for entry in entries)
        snapshots, latest_jobs = await asyncio.gather(
            self._services.store.get_current_many_async(company_ids),
            self._services.store.get_latest_jobs_async(company_ids),
        )
        companies: list[BiCompanySummary] = []
        for entry in entries:
            company_id = entry.company.company_id
            companies.append(
                build_company_summary(
                    entry,
                    snapshots.get(company_id),
                    latest_jobs.get(company_id),
                )
            )
        return BiCompanyListResponse(companies=tuple(companies))

    async def list_materialization_candidates(
        self,
    ) -> BiMaterializationCandidateListResponse:
        entries = await self._services.store.list_companies_async()
        if not entries:
            return BiMaterializationCandidateListResponse(candidates=())
        company_ids = tuple(entry.company.company_id for entry in entries)
        snapshots, latest_jobs = await asyncio.gather(
            self._services.store.get_current_many_async(company_ids),
            self._services.store.get_latest_jobs_async(company_ids),
        )
        candidates = tuple(
            candidate
            for entry in entries
            if (
                candidate := build_materialization_candidate(
                    entry,
                    snapshots.get(entry.company.company_id),
                    latest_jobs.get(entry.company.company_id),
                )
            )
            is not None
        )
        return BiMaterializationCandidateListResponse(candidates=candidates)

    async def get_dashboard(self, company_id: CompanyId) -> BiDashboardResult:
        company, snapshot, latest_job = await asyncio.gather(
            self._services.store.get_company_async(company_id),
            self._services.store.get_current_async(company_id),
            self._services.store.get_latest_job_async(company_id),
        )
        if company is None:
            raise BiNotFoundError(COMPANY_NOT_FOUND)
        if snapshot is None:
            if latest_job is None:
                raise BiNotFoundError(DASHBOARD_NOT_AVAILABLE)
            return BiDashboardResult(pending_job=latest_job)
        return BiDashboardResult(snapshot=with_refresh_state(snapshot, latest_job))

    async def delete_dashboard(self, company_id: CompanyId) -> None:
        company = await self._services.store.get_company_async(company_id)
        if company is None:
            raise BiNotFoundError(COMPANY_NOT_FOUND)
        try:
            deleted = await self._services.store.delete_dashboard_snapshot_async(
                company_id
            )
        except BiDashboardDeleteActiveError as error:
            raise BiConflictError("company BI work is active") from error
        if not deleted:
            raise BiNotFoundError(DASHBOARD_NOT_AVAILABLE)

    async def create_materialization(
        self,
        request: BiMaterializationRequest,
    ) -> BiMaterializationAccepted:
        existing = await self._services.store.find_latest_job_async(
            request.company_id
        )
        if existing is not None and existing.status is not MaterializationStatus.FAILED:
            if existing.workbook_hash == request.source.workbook_hash:
                return accepted(existing)
            if is_active(existing.status):
                raise BiConflictError(MATERIALIZATION_ACTIVE)

        now = self._services.clock.now()
        queued = BiMaterializationJob(
            job_id=job_id_for(request),
            company_id=request.company_id,
            workbook_hash=request.source.workbook_hash,
            status=MaterializationStatus.QUEUED,
            completed_requests=0,
            total_requests=0,
            started_at=now,
            updated_at=now,
        )
        try:
            persisted = await self._services.materializations.enqueue_async(
                request,
                queued,
            )
        except BiPostgresStoreError as error:
            raise BiQueueUnavailableError(
                "BI Kubernetes queue is unavailable"
            ) from error
        return accepted(persisted)

    async def get_materialization(self, job_id: JobId) -> BiMaterializationJob:
        job = await self._services.store.get_job_async(job_id)
        if job is None:
            raise BiNotFoundError(JOB_NOT_FOUND)
        return job

    def load_materialization(self, job_id: str) -> BiMaterializationJob:
        job = self._services.store.get_job(JobId(job_id))
        if job is None:
            raise BiNotFoundError(JOB_NOT_FOUND)
        if job.status is MaterializationStatus.MATERIALIZING:
            progress = self._services.questions.get_job_progress(JobId(job_id))
            if progress is not None:
                job = self._with_question_progress(job, progress)
        return job

    async def load_materialization_async(self, job_id: str) -> BiMaterializationJob:
        job = await self._services.store.get_job_async(JobId(job_id))
        if job is None:
            raise BiNotFoundError(JOB_NOT_FOUND)
        if job.status is MaterializationStatus.MATERIALIZING:
            progress = await self._services.questions.get_job_progress_async(
                JobId(job_id)
            )
            if progress is not None:
                job = self._with_question_progress(job, progress)
        return job

    def refresh_dashboard(self, company_id: CompanyId) -> BiDashboardSnapshot:
        _, snapshot = self._require_dashboard(company_id)
        created_at = self._services.clock.now()
        identity = "\x00".join(
            (
                str(company_id),
                str(snapshot.snapshot.snapshot_id),
                snapshot.source.workbook_hash,
                str(snapshot.source.index_id),
                created_at.isoformat(),
            )
        )
        job_id = JobId(
            "recalculation-" + sha256(identity.encode("utf-8")).hexdigest()[:24]
        )
        try:
            return recalculate_dashboard(
                store=self._services.store,
                company_id=company_id,
                job_id=job_id,
                generated_at=created_at,
            )
        except BiDashboardRecalculationError as error:
            raise BiConflictError(str(error)) from error

    def reset_dashboard(self, company_id: CompanyId) -> BiQuestionJobProgress:
        company, snapshot = self._require_dashboard(company_id)
        created_at = self._services.clock.now()
        identity = "\x00".join(
            (
                str(company_id),
                snapshot.source.workbook_hash,
                str(snapshot.source.index_id),
                created_at.isoformat(),
            )
        )
        job_id = JobId(
            "question-reset-" + sha256(identity.encode("utf-8")).hexdigest()[:24]
        )
        try:
            return self._services.questions.reset_materialization_questions(
                BiQuestionBatchPlan(
                    materialization=BiMaterializationRequest(
                        company_id=company.company_id,
                        display_name=company.display_name,
                        source=snapshot.source,
                    ),
                    periods=snapshot.periods,
                    job_id=job_id,
                    created_at=created_at,
                )
            )
        except BiQuestionResetActiveError as error:
            raise BiConflictError(
                "BI questions are already active for this company"
            ) from error
        except (BiQuestionRepositoryError, BiQuestionRegistrationError) as error:
            raise BiQueueUnavailableError(
                "BI question Kubernetes queue is unavailable"
            ) from error

    async def get_question_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress:
        progress = await self._services.questions.get_job_progress_async(job_id)
        if progress is None:
            raise BiNotFoundError(QUESTION_JOB_NOT_FOUND)
        return progress

    def load_question_progress(self, job_id: str) -> BiQuestionJobProgress:
        progress = self._services.questions.get_job_progress(JobId(job_id))
        if progress is None:
            raise BiNotFoundError(QUESTION_JOB_NOT_FOUND)
        return progress

    async def load_question_progress_async(
        self,
        job_id: str,
    ) -> BiQuestionJobProgress:
        return await self.get_question_progress(JobId(job_id))

    def _require_dashboard(
        self,
        company_id: CompanyId,
    ) -> tuple[BiCompany, BiDashboardSnapshot]:
        company = self._services.store.get_company(company_id)
        if company is None:
            raise BiNotFoundError(COMPANY_NOT_FOUND)
        snapshot = self._services.store.get_current(company_id)
        if snapshot is None:
            raise BiNotFoundError(DASHBOARD_NOT_AVAILABLE)
        if not snapshot.periods:
            raise BiConflictError(REFRESH_PERIODS_UNAVAILABLE)
        return company, snapshot

    @staticmethod
    def _with_question_progress(
        job: BiMaterializationJob,
        progress: BiQuestionJobProgress,
    ) -> BiMaterializationJob:
        completed = progress.completed_questions + progress.failed_questions
        return job.model_copy(
            update={
                "completed_requests": completed,
                "total_requests": progress.total_questions,
                "message": (
                    f"지표 질문 {completed}/{progress.total_questions}건을 "
                    "병렬 처리했습니다."
                ),
            }
        )


__all__ = [
    "COMPANY_NOT_FOUND",
    "DASHBOARD_NOT_AVAILABLE",
    "JOB_NOT_FOUND",
    "MATERIALIZATION_ACTIVE",
    "QUESTION_JOB_NOT_FOUND",
    "REFRESH_PERIODS_UNAVAILABLE",
    "BiApplicationService",
    "BiConflictError",
    "BiDashboardResult",
    "BiNotFoundError",
    "BiQueueUnavailableError",
]
