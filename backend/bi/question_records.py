from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, Literal, NewType, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from .extraction_models import BiMetricExtractionResult
from .models import (
    IDENTIFIER_PATTERN,
    WORKBOOK_HASH_PATTERN,
    BiContractModel,
    CompanyId,
    IndexId,
    JobId,
    MetricId,
    PeriodId,
)


QuestionId = NewType("QuestionId", str)
AnswerId = NewType("AnswerId", str)
QuestionVersion = NewType("QuestionVersion", str)
WorkflowRunId = NewType("WorkflowRunId", str)


@unique
class BiQuestionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@unique
class BiAnswerOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class BiQuestionRecord(BiContractModel):
    question_id: QuestionId = Field(pattern=IDENTIFIER_PATTERN)
    materialization_job_id: JobId = Field(pattern=IDENTIFIER_PATTERN)
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    workbook_hash: str = Field(pattern=WORKBOOK_HASH_PATTERN)
    index_id: IndexId = Field(pattern=IDENTIFIER_PATTERN)
    metric_id: MetricId
    period_id: PeriodId = Field(pattern=IDENTIFIER_PATTERN)
    question_version: QuestionVersion = Field(pattern=IDENTIFIER_PATTERN)
    question_text: str = Field(min_length=1, max_length=2_000)
    status: BiQuestionStatus
    workflow_run_id: WorkflowRunId | None = Field(
        default=None,
        pattern=IDENTIFIER_PATTERN,
    )
    attempt_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def require_consistent_state(self) -> "BiQuestionRecord":
        match self.status:
            case BiQuestionStatus.QUEUED:
                timestamps_are_valid = (
                    self.started_at is None and self.completed_at is None
                )
            case BiQuestionStatus.RUNNING:
                timestamps_are_valid = (
                    self.started_at is not None and self.completed_at is None
                )
            case BiQuestionStatus.COMPLETED | BiQuestionStatus.FAILED:
                timestamps_are_valid = (
                    self.started_at is not None and self.completed_at is not None
                )
            case unreachable:
                assert_never(unreachable)
        if not timestamps_are_valid or self.updated_at < self.created_at:
            raise PydanticCustomError(
                "invalid_question_state",
                "question timestamps do not match its status",
            )
        return self


class BiAnswerRecordBase(BiContractModel):
    answer_id: AnswerId = Field(pattern=IDENTIFIER_PATTERN)
    question_id: QuestionId = Field(pattern=IDENTIFIER_PATTERN)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    latency_ms: int = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def require_monotonic_timestamps(self) -> "BiAnswerRecordBase":
        if self.updated_at < self.created_at:
            raise PydanticCustomError(
                "invalid_answer_timestamps",
                "answer updated_at precedes created_at",
            )
        return self


class BiCompletedAnswerRecord(BiAnswerRecordBase):
    outcome: Literal[BiAnswerOutcome.COMPLETED]
    answer_text: str = Field(min_length=1, max_length=50_000)
    result: BiMetricExtractionResult
    evidence_cell_ids: tuple[str, ...]
    error_code: None = None
    error_message: None = None


class BiFailedAnswerRecord(BiAnswerRecordBase):
    outcome: Literal[BiAnswerOutcome.FAILED]
    answer_text: None = None
    result: None = None
    evidence_cell_ids: tuple[()] = ()
    error_code: str = Field(pattern=r"^[a-z][a-z0-9._-]{0,127}$")
    error_message: str = Field(min_length=1, max_length=2_000)


BiAnswerRecord = Annotated[
    BiCompletedAnswerRecord | BiFailedAnswerRecord,
    Field(discriminator="outcome"),
]


class BiQuestionBatch(BiContractModel):
    questions: tuple[BiQuestionRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_one_queued_job(self) -> "BiQuestionBatch":
        job_ids = {
            question.materialization_job_id for question in self.questions
        }
        identities = {
            (
                question.metric_id,
                question.period_id,
                question.question_version,
            )
            for question in self.questions
        }
        questions_are_queued = all(
            question.status is BiQuestionStatus.QUEUED
            for question in self.questions
        )
        if (
            len(job_ids) != 1
            or len(identities) != len(self.questions)
            or not questions_are_queued
        ):
            raise PydanticCustomError(
                "invalid_question_batch",
                "question batch must contain unique queued questions for one job",
            )
        return self


class BiQuestionStart(BiContractModel):
    question_id: QuestionId = Field(pattern=IDENTIFIER_PATTERN)
    workflow_run_id: WorkflowRunId = Field(pattern=IDENTIFIER_PATTERN)
    started_at: datetime


class BiQuestionClaim(BiContractModel):
    workflow_run_id: WorkflowRunId = Field(pattern=IDENTIFIER_PATTERN)
    claimed_at: datetime


class BiQuestionJobProgress(BiContractModel):
    job_id: JobId = Field(pattern=IDENTIFIER_PATTERN)
    total_questions: int = Field(ge=1)
    queued_questions: int = Field(ge=0)
    running_questions: int = Field(ge=0)
    completed_questions: int = Field(ge=0)
    failed_questions: int = Field(ge=0)

    @model_validator(mode="after")
    def require_complete_status_partition(self) -> "BiQuestionJobProgress":
        status_total = (
            self.queued_questions
            + self.running_questions
            + self.completed_questions
            + self.failed_questions
        )
        if status_total != self.total_questions:
            raise PydanticCustomError(
                "question_progress_mismatch",
                "question status counts must equal total_questions",
            )
        return self


class BiLatestAnswerQuery(BiContractModel):
    company_id: CompanyId = Field(pattern=IDENTIFIER_PATTERN)
    workbook_hash: str = Field(pattern=WORKBOOK_HASH_PATTERN)
    index_id: IndexId = Field(pattern=IDENTIFIER_PATTERN)
