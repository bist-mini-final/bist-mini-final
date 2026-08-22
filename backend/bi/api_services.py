from dataclasses import dataclass
from typing import Protocol

from .materialization_models import BiCompanyIndexEntry, BiMaterializationOutcome
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

    def get_job(self, job_id: JobId) -> BiMaterializationJob | None: ...

    def get_latest_job(
        self,
        company_id: CompanyId,
    ) -> BiMaterializationJob | None: ...

    def find_latest_job(
        self,
        company_id: CompanyId,
        workbook_hash: str,
    ) -> BiMaterializationJob | None: ...


class BiMaterializationRunnerPort(Protocol):
    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome: ...


class BiInitialSnapshotPort(Protocol):
    def materialize(
        self,
        company: BiCompany,
        workbook_hash: str,
    ) -> BiDashboardSnapshot | None: ...


class BiQuestionApiPort(Protocol):
    def queue_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> BiQuestionJobProgress: ...

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None: ...


@dataclass(frozen=True, slots=True)
class BiApiServices:
    store: BiApiStorePort
    runner: BiMaterializationRunnerPort
    clock: ClockPort
    questions: BiQuestionApiPort
    initial_snapshots: BiInitialSnapshotPort | None = None
