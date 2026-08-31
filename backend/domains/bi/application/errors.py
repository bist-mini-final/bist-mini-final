"""Stable errors exposed by BI application ports and use cases."""

from dataclasses import dataclass

from backend.domains.bi.domain.models import CompanyId, JobId
from backend.domains.bi.domain.question_records import BiQuestionStatus, QuestionId


class BiProviderError(RuntimeError):
    """An external completion or retrieval provider failed."""


@dataclass(frozen=True, slots=True)
class BiQuestionSourceError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class BiPostgresStoreError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"BI PostgreSQL store {self.operation} failed: {self.reason}"


@dataclass(frozen=True, slots=True)
class BiDashboardDeleteActiveError(RuntimeError):
    company_id: CompanyId

    def __str__(self) -> str:
        return f"BI work is active for company: {self.company_id}"


@dataclass(frozen=True, slots=True)
class BiDocumentProfileRepositoryError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"BI document profile {self.operation} failed: {self.reason}"


@dataclass(frozen=True, slots=True)
class BiQuestionRepositoryError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"BI question repository {self.operation} failed: {self.reason}"


@dataclass(frozen=True, slots=True)
class BiQuestionRegistrationError(RuntimeError):
    materialization_job_id: JobId

    def __str__(self) -> str:
        return f"BI question batch was not fully registered: {self.materialization_job_id}"


@dataclass(frozen=True, slots=True)
class BiQuestionResetActiveError(RuntimeError):
    company_id: str

    def __str__(self) -> str:
        return f"BI questions are active for company: {self.company_id}"


@dataclass(frozen=True, slots=True)
class BiQuestionTransitionError(RuntimeError):
    question_id: QuestionId
    expected_status: BiQuestionStatus

    def __str__(self) -> str:
        return f"BI question {self.question_id} is not in {self.expected_status.value} state"


@dataclass(frozen=True, slots=True)
class BiQuestionSnapshotRepositoryError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"BI question snapshot query failed: {self.reason}"


__all__ = [
    "BiDashboardDeleteActiveError",
    "BiDocumentProfileRepositoryError",
    "BiPostgresStoreError",
    "BiProviderError",
    "BiQuestionRegistrationError",
    "BiQuestionRepositoryError",
    "BiQuestionResetActiveError",
    "BiQuestionSourceError",
    "BiQuestionSnapshotRepositoryError",
    "BiQuestionTransitionError",
]
