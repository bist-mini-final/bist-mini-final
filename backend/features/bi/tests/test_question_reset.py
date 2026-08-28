from datetime import UTC, date, datetime

from backend.features.bi.models import (
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    CompanyId,
    IndexId,
    JobId,
    PeriodId,
    PeriodKind,
)
from backend.features.bi.question_batch import BiQuestionBatchPlan
from backend.features.bi.question_records import (
    BiAnswerRecord,
    BiCompletedAnswerRecord,
    BiLatestAnswerQuery,
    BiQuestionClaim,
    BiQuestionJobProgress,
    BiQuestionRecord,
    BiQuestionStart,
    QuestionId,
    WorkflowRunId,
)
from backend.features.bi.question_service import (
    BiQuestionRepositoryPort,
    BiQuestionService,
)

AS_OF = datetime(2026, 8, 25, tzinfo=UTC)


class ResetRepository(BiQuestionRepositoryPort):
    def __init__(self) -> None:
        self.replaced: tuple[BiQuestionRecord, ...] = ()

    def register_questions(
        self,
        questions: tuple[BiQuestionRecord, ...],
    ) -> tuple[BiQuestionRecord, ...]:
        raise AssertionError("reset must replace, not append, question rows")

    def replace_questions(
        self,
        questions: tuple[BiQuestionRecord, ...],
    ) -> tuple[BiQuestionRecord, ...]:
        self.replaced = questions
        return questions

    def get_question(self, question_id: QuestionId) -> BiQuestionRecord | None:
        raise AssertionError("reset must not fetch individual questions")

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]:
        raise AssertionError("reset must not list stored questions")

    def get_job_progress(self, job_id: JobId) -> BiQuestionJobProgress | None:
        raise AssertionError("reset must summarize the replacement batch")

    async def get_job_progress_async(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None:
        raise AssertionError("reset must not load async progress")

    def claim_next(
        self,
        command: BiQuestionClaim,
    ) -> BiQuestionRecord | None:
        raise AssertionError("reset must not claim questions")

    def claim_next_batch(
        self,
        command: BiQuestionClaim,
        batch_size: int,
    ) -> tuple[BiQuestionRecord, ...]:
        raise AssertionError("reset must not claim question batches")

    def start_question(self, command: BiQuestionStart) -> BiQuestionRecord:
        raise AssertionError("reset must not start questions")

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord:
        raise AssertionError("reset must not save answers")

    def heartbeat(
        self,
        question_id: QuestionId,
        workflow_run_id: WorkflowRunId,
    ) -> bool:
        raise AssertionError("reset must not update heartbeats")

    def latest_answers(
        self,
        query: BiLatestAnswerQuery,
    ) -> tuple[BiCompletedAnswerRecord, ...]:
        raise AssertionError("reset must not query answers")


def reset_plan() -> BiQuestionBatchPlan:
    period = BiPeriod(
        period_id=PeriodId("fy-2025"),
        kind=PeriodKind.FY,
        label="FY2025",
        source_label="FY2025",
        end_date=date(2025, 12, 31),
        ordinal=2025,
    )
    return BiQuestionBatchPlan(
        materialization=BiMaterializationRequest(
            company_id=CompanyId("company-test"),
            display_name="Test Company",
            source=BiMaterializationSource(
                file_name="test.xlsx",
                workbook_hash="a" * 64,
                index_id=IndexId("index-test"),
            ),
        ),
        periods=(period,),
        job_id=JobId("question-reset-test"),
        created_at=AS_OF,
    )


def test_reset_replaces_current_company_questions_instead_of_appending() -> None:
    repository = ResetRepository()
    service = BiQuestionService(repository)
    plan = reset_plan()

    progress = service.reset_materialization_questions(plan)

    assert repository.replaced
    assert {question.company_id for question in repository.replaced} == {
        plan.materialization.company_id
    }
    assert {question.workbook_hash for question in repository.replaced} == {
        plan.materialization.source.workbook_hash
    }
    assert progress.job_id == plan.job_id
    assert progress.queued_questions == progress.total_questions
