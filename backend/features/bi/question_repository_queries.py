from dataclasses import dataclass
from typing import Final

import psycopg
import psycopg2
from psycopg.rows import dict_row
from psycopg2.extras import RealDictCursor
from pydantic import TypeAdapter

from backend.domains.bi.domain.question_records import (
    BiAnswerOutcome,
    BiCompletedAnswerRecord,
    BiLatestAnswerQuery,
    BiQuestionJobProgress,
    BiQuestionRecord,
    BiQuestionStatus,
    JobId,
    QuestionId,
)
from backend.platform.postgres.pool import (
    get_pooled_async_connection,
    get_pooled_raw_connection,
)

QUESTION_COLUMNS: Final = (
    "question_id, materialization_job_id, company_id, workbook_hash, index_id, "
    "metric_id, period_id, question_version, question_text, status, "
    "workflow_run_id, attempt_count, created_at, updated_at, started_at, completed_at"
)
COMPLETED_ANSWER_ADAPTER: Final = TypeAdapter(BiCompletedAnswerRecord)
QUESTION_PROGRESS_QUERY: Final = (
    "SELECT materialization_job_id AS job_id, "
    "COUNT(*) AS total_questions, "
    "COUNT(*) FILTER (WHERE status = %s) AS queued_questions, "
    "COUNT(*) FILTER (WHERE status = %s) AS running_questions, "
    "COUNT(*) FILTER (WHERE status = %s) AS completed_questions, "
    "COUNT(*) FILTER (WHERE status = %s) AS failed_questions "
    "FROM bi_questions WHERE materialization_job_id = %s "
    "GROUP BY materialization_job_id"
)


@dataclass(frozen=True, slots=True)
class BiQuestionRepositoryError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"BI question repository {self.operation} failed: {self.reason}"


class PostgresBiQuestionQueries:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_question(self, question_id: QuestionId) -> BiQuestionRecord | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"SELECT {QUESTION_COLUMNS} FROM bi_questions WHERE question_id = %s",
                        (question_id,),
                    )
                    row = cursor.fetchone()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="get",
                reason=str(error),
            ) from error
        return BiQuestionRecord.model_validate(row) if row is not None else None

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"SELECT {QUESTION_COLUMNS} FROM bi_questions "
                        "WHERE materialization_job_id = %s "
                        "ORDER BY metric_id, period_id",
                        (job_id,),
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="list",
                reason=str(error),
            ) from error
        return tuple(BiQuestionRecord.model_validate(row) for row in rows)

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        QUESTION_PROGRESS_QUERY,
                        self._progress_parameters(job_id),
                    )
                    row = cursor.fetchone()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="get_job_progress",
                reason=str(error),
            ) from error
        return BiQuestionJobProgress.model_validate(row) if row is not None else None

    async def get_job_progress_async(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None:
        try:
            async with get_pooled_async_connection(self._database_url) as connection:
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        QUESTION_PROGRESS_QUERY,
                        self._progress_parameters(job_id),
                    )
                    row = await cursor.fetchone()
        except psycopg.Error as error:
            raise BiQuestionRepositoryError(
                operation="get_job_progress",
                reason=str(error),
            ) from error
        return BiQuestionJobProgress.model_validate(row) if row is not None else None

    @staticmethod
    def _progress_parameters(job_id: JobId) -> tuple[str, str, str, str, JobId]:
        return (
            BiQuestionStatus.QUEUED.value,
            BiQuestionStatus.RUNNING.value,
            BiQuestionStatus.COMPLETED.value,
            BiQuestionStatus.FAILED.value,
            job_id,
        )

    def latest_answers(
        self,
        query: BiLatestAnswerQuery,
    ) -> tuple[BiCompletedAnswerRecord, ...]:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT DISTINCT ON (q.metric_id, q.period_id) "
                        "a.answer_id, a.question_id, q.workflow_run_id, "
                        "a.outcome, a.answer_text, "
                        "a.answer_payload AS result, a.evidence_cell_ids, "
                        "a.error_code, a.error_message, a.model_name, a.latency_ms, "
                        "a.prompt_tokens, a.completion_tokens, a.created_at, a.updated_at "
                        "FROM bi_questions q JOIN bi_answers a ON a.question_id = q.question_id "
                        "WHERE q.company_id = %s AND q.workbook_hash = %s AND q.index_id = %s "
                        "AND q.status = %s AND a.outcome = %s "
                        "ORDER BY q.metric_id, q.period_id, q.completed_at DESC, a.updated_at DESC",
                        (
                            query.company_id,
                            query.workbook_hash,
                            query.index_id,
                            BiQuestionStatus.COMPLETED.value,
                            BiAnswerOutcome.COMPLETED.value,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="latest_answers",
                reason=str(error),
            ) from error
        return tuple(COMPLETED_ANSWER_ADAPTER.validate_python(row) for row in rows)
