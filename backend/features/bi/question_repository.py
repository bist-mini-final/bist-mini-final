from dataclasses import dataclass
from typing import assert_never

import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values

from backend.core.settings import PGVECTOR_URL
from backend.domains.bi.domain.question_records import (
    BiAnswerRecord,
    BiCompletedAnswerRecord,
    BiFailedAnswerRecord,
    BiLatestAnswerQuery,
    BiQuestionClaim,
    BiQuestionJobProgress,
    BiQuestionRecord,
    BiQuestionStart,
    BiQuestionStatus,
    JobId,
    QuestionId,
    WorkflowRunId,
)
from backend.storage.connection_pool import get_pooled_raw_connection

from .question_claim_repository import PostgresBiQuestionClaimer
from .question_repository_queries import (
    QUESTION_COLUMNS,
    BiQuestionRepositoryError,
    PostgresBiQuestionQueries,
)


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


class PostgresBiQuestionRepository:
    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self._database_url = database_url
        self._claimer = PostgresBiQuestionClaimer(database_url)
        self._queries = PostgresBiQuestionQueries(database_url)

    def register_questions(
        self,
        questions: tuple[BiQuestionRecord, ...],
    ) -> tuple[BiQuestionRecord, ...]:
        job_id = questions[0].materialization_job_id
        values = [
            (
                question.question_id,
                question.materialization_job_id,
                question.company_id,
                question.workbook_hash,
                question.index_id,
                question.metric_id.value,
                question.period_id,
                question.question_version,
                question.question_text,
                question.status.value,
                question.workflow_run_id,
                question.attempt_count,
                question.created_at,
                question.updated_at,
                question.started_at,
                question.completed_at,
            )
            for question in questions
        ]
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    execute_values(
                        cursor,
                        f"INSERT INTO bi_questions ({QUESTION_COLUMNS}) VALUES %s "
                        "ON CONFLICT (materialization_job_id, metric_id, period_id, question_version) "
                        f"DO UPDATE SET status = '{BiQuestionStatus.QUEUED.value}', "
                        "workflow_run_id = NULL, "
                        "started_at = NULL, completed_at = NULL, "
                        "updated_at = EXCLUDED.updated_at "
                        f"WHERE bi_questions.status = '{BiQuestionStatus.FAILED.value}'",
                        values,
                    )
                    cursor.execute(
                        f"SELECT {QUESTION_COLUMNS} FROM bi_questions "
                        "WHERE materialization_job_id = %s",
                        (job_id,),
                    )
                    stored = tuple(
                        BiQuestionRecord.model_validate(row) for row in cursor.fetchall()
                    )
                    stored_by_identity = {
                        (
                            record.metric_id,
                            record.period_id,
                            record.question_version,
                        ): record
                        for record in stored
                    }
                    all_registered = all(
                        (
                            question.metric_id,
                            question.period_id,
                            question.question_version,
                        )
                        in stored_by_identity
                        for question in questions
                    )
                    if not all_registered:
                        raise BiQuestionRegistrationError(materialization_job_id=job_id)
                    registered = tuple(
                        stored_by_identity[
                            (
                                question.metric_id,
                                question.period_id,
                                question.question_version,
                            )
                        ]
                        for question in questions
                    )
                connection.commit()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="register",
                reason=str(error),
            ) from error
        return registered

    def replace_questions(
        self,
        questions: tuple[BiQuestionRecord, ...],
    ) -> tuple[BiQuestionRecord, ...]:
        first = questions[0]
        values = [
            (
                question.question_id,
                question.materialization_job_id,
                question.company_id,
                question.workbook_hash,
                question.index_id,
                question.metric_id.value,
                question.period_id,
                question.question_version,
                question.question_text,
                question.status.value,
                question.workflow_run_id,
                question.attempt_count,
                question.created_at,
                question.updated_at,
                question.started_at,
                question.completed_at,
            )
            for question in questions
        ]
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT company_id FROM bi_companies WHERE company_id = %s FOR UPDATE",
                        (first.company_id,),
                    )
                    cursor.execute(
                        "SELECT question_id FROM bi_questions "
                        "WHERE company_id = %s AND workbook_hash = %s "
                        "AND index_id = %s AND status IN (%s, %s) "
                        "LIMIT 1 FOR UPDATE",
                        (
                            first.company_id,
                            first.workbook_hash,
                            first.index_id,
                            BiQuestionStatus.QUEUED.value,
                            BiQuestionStatus.RUNNING.value,
                        ),
                    )
                    if cursor.fetchone() is not None:
                        raise BiQuestionResetActiveError(str(first.company_id))
                    cursor.execute(
                        "DELETE FROM bi_questions "
                        "WHERE company_id = %s AND workbook_hash = %s "
                        "AND index_id = %s",
                        (
                            first.company_id,
                            first.workbook_hash,
                            first.index_id,
                        ),
                    )
                    execute_values(
                        cursor,
                        f"INSERT INTO bi_questions ({QUESTION_COLUMNS}) VALUES %s",
                        values,
                    )
                    cursor.execute(
                        f"SELECT {QUESTION_COLUMNS} FROM bi_questions "
                        "WHERE materialization_job_id = %s "
                        "ORDER BY metric_id, period_id",
                        (first.materialization_job_id,),
                    )
                    registered = tuple(
                        BiQuestionRecord.model_validate(row) for row in cursor.fetchall()
                    )
                    if len(registered) != len(questions):
                        raise BiQuestionRegistrationError(
                            materialization_job_id=first.materialization_job_id
                        )
                connection.commit()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="replace",
                reason=str(error),
            ) from error
        return registered

    def get_question(self, question_id: QuestionId) -> BiQuestionRecord | None:
        return self._queries.get_question(question_id)

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]:
        return self._queries.list_questions(job_id)

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None:
        return self._queries.get_job_progress(job_id)

    async def get_job_progress_async(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None:
        return await self._queries.get_job_progress_async(job_id)

    def claim_next(
        self,
        command: BiQuestionClaim,
    ) -> BiQuestionRecord | None:
        return self._claimer.claim_next(command)

    def claim_next_batch(
        self,
        command: BiQuestionClaim,
        batch_size: int = 16,
    ) -> tuple[BiQuestionRecord, ...]:
        return self._claimer.claim_next_batch(command, batch_size=batch_size)

    def start_question(self, command: BiQuestionStart) -> BiQuestionRecord:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"UPDATE bi_questions SET status = %s, workflow_run_id = %s, "
                        "attempt_count = attempt_count + 1, started_at = %s, "
                        "completed_at = NULL, updated_at = %s "
                        "WHERE question_id = %s AND status IN (%s, %s) "
                        f"RETURNING {QUESTION_COLUMNS}",
                        (
                            BiQuestionStatus.RUNNING.value,
                            command.workflow_run_id,
                            command.started_at,
                            command.started_at,
                            command.question_id,
                            BiQuestionStatus.QUEUED.value,
                            BiQuestionStatus.FAILED.value,
                        ),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise BiQuestionTransitionError(
                            question_id=command.question_id,
                            expected_status=BiQuestionStatus.QUEUED,
                        )
                    question = BiQuestionRecord.model_validate(row)
                connection.commit()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="start",
                reason=str(error),
            ) from error
        return question

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord:
        match answer:
            case BiCompletedAnswerRecord(result=result):
                status = BiQuestionStatus.COMPLETED
                payload = Json(result.model_dump(mode="json"))
            case BiFailedAnswerRecord():
                status = BiQuestionStatus.FAILED
                payload = None
            case unreachable:
                assert_never(unreachable)
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"UPDATE bi_questions SET status = %s, completed_at = %s, "
                        "updated_at = %s WHERE question_id = %s AND status = %s "
                        "AND workflow_run_id = %s "
                        f"RETURNING {QUESTION_COLUMNS}",
                        (
                            status.value,
                            answer.updated_at,
                            answer.updated_at,
                            answer.question_id,
                            BiQuestionStatus.RUNNING.value,
                            answer.workflow_run_id,
                        ),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise BiQuestionTransitionError(
                            question_id=answer.question_id,
                            expected_status=BiQuestionStatus.RUNNING,
                        )
                    question = BiQuestionRecord.model_validate(row)
                    cursor.execute(
                        "INSERT INTO bi_answers (answer_id, question_id, outcome, "
                        "answer_text, answer_payload, evidence_cell_ids, error_code, "
                        "error_message, model_name, latency_ms, prompt_tokens, "
                        "completion_tokens, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (question_id) DO UPDATE SET "
                        "answer_id = EXCLUDED.answer_id, outcome = EXCLUDED.outcome, "
                        "answer_text = EXCLUDED.answer_text, answer_payload = EXCLUDED.answer_payload, "
                        "evidence_cell_ids = EXCLUDED.evidence_cell_ids, error_code = EXCLUDED.error_code, "
                        "error_message = EXCLUDED.error_message, model_name = EXCLUDED.model_name, "
                        "latency_ms = EXCLUDED.latency_ms, prompt_tokens = EXCLUDED.prompt_tokens, "
                        "completion_tokens = EXCLUDED.completion_tokens, "
                        "created_at = LEAST(bi_answers.created_at, EXCLUDED.created_at), "
                        "updated_at = EXCLUDED.updated_at",
                        (
                            answer.answer_id,
                            answer.question_id,
                            answer.outcome.value,
                            answer.answer_text,
                            payload,
                            Json(list(answer.evidence_cell_ids)),
                            answer.error_code,
                            answer.error_message,
                            answer.model_name,
                            answer.latency_ms,
                            answer.prompt_tokens,
                            answer.completion_tokens,
                            answer.created_at,
                            answer.updated_at,
                        ),
                    )
                connection.commit()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="save_answer",
                reason=str(error),
            ) from error
        return question

    def heartbeat(
        self,
        question_id: QuestionId,
        workflow_run_id: WorkflowRunId,
    ) -> bool:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE bi_questions SET updated_at = NOW() "
                        "WHERE question_id = %s AND workflow_run_id = %s "
                        "AND status = %s",
                        (
                            question_id,
                            workflow_run_id,
                            BiQuestionStatus.RUNNING.value,
                        ),
                    )
                    updated = cursor.rowcount == 1
                connection.commit()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="heartbeat",
                reason=str(error),
            ) from error
        return updated

    def latest_answers(
        self,
        query: BiLatestAnswerQuery,
    ) -> tuple[BiCompletedAnswerRecord, ...]:
        return self._queries.latest_answers(query)
