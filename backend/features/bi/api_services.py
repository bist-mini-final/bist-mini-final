from dataclasses import dataclass
from typing import Protocol

from .materialization_models import BiCompanyIndexEntry
from .materializer import ClockPort
from .models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    CompanyId,
    JobId,
)
from .question_batch import BiQuestionBatchPlan
from .question_records import BiQuestionJobProgress


class BiApiStorePort(Protocol):
    def register_company(self, company: BiCompany) -> None: ...

    def save_job(self, job: BiMaterializationJob) -> None: ...

    def get_company(self, company_id: CompanyId) -> BiCompany | None: ...

    def list_companies(self) -> tuple[BiCompanyIndexEntry, ...]: ...

    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None: ...

    def publish(self, snapshot: BiDashboardSnapshot) -> None: ...

    def get_current_many(
        self,
        company_ids: tuple[CompanyId, ...],
    ) -> dict[CompanyId, BiDashboardSnapshot]: ...

    def get_job(self, job_id: JobId) -> BiMaterializationJob | None: ...

    def get_latest_job(
        self,
        company_id: CompanyId,
    ) -> BiMaterializationJob | None: ...

    def get_latest_jobs(
        self,
        company_ids: tuple[CompanyId, ...],
    ) -> dict[CompanyId, BiMaterializationJob]: ...

    def find_latest_job(
        self,
        company_id: CompanyId,
    ) -> BiMaterializationJob | None: ...

    async def get_company_async(
        self,
        company_id: CompanyId,
    ) -> BiCompany | None: ...

    async def list_companies_async(self) -> tuple[BiCompanyIndexEntry, ...]: ...

    async def get_current_async(
        self,
        company_id: CompanyId,
    ) -> BiDashboardSnapshot | None: ...

    async def get_current_many_async(
        self,
        company_ids: tuple[CompanyId, ...],
    ) -> dict[CompanyId, BiDashboardSnapshot]: ...

    async def get_job_async(
        self,
        job_id: JobId,
    ) -> BiMaterializationJob | None: ...

    async def get_latest_job_async(
        self,
        company_id: CompanyId,
    ) -> BiMaterializationJob | None: ...

    async def get_latest_jobs_async(
        self,
        company_ids: tuple[CompanyId, ...],
    ) -> dict[CompanyId, BiMaterializationJob]: ...

    async def find_latest_job_async(
        self,
        company_id: CompanyId,
    ) -> BiMaterializationJob | None: ...

    async def delete_dashboard_snapshot_async(
        self,
        company_id: CompanyId,
    ) -> bool: ...


class BiMaterializationQueuePort(Protocol):
    def enqueue(
        self,
        request: BiMaterializationRequest,
        job: BiMaterializationJob,
    ) -> BiMaterializationJob: ...

    async def enqueue_async(
        self,
        request: BiMaterializationRequest,
        job: BiMaterializationJob,
    ) -> BiMaterializationJob: ...


class BiQuestionApiPort(Protocol):
    def queue_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> BiQuestionJobProgress: ...

    def reset_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> BiQuestionJobProgress: ...

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None: ...

    async def get_job_progress_async(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None: ...


@dataclass(frozen=True, slots=True)
class BiApiServices:
    store: BiApiStorePort
    materializations: BiMaterializationQueuePort
    clock: ClockPort
    questions: BiQuestionApiPort
