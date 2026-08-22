from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import ValidationError

from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection

from .extraction_models import BiMetricExtractionResult
from .initial_snapshot import BiPersistedAnswerBatch
from .models import CompanyId, JobId
from .question_records import BiAnswerOutcome, BiQuestionRecord, BiQuestionStatus


@dataclass(frozen=True, slots=True)
class BiQuestionSnapshotRepositoryError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"BI question snapshot query failed: {self.reason}"


class PostgresBiQuestionSnapshotRepository:
    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self._database_url = database_url

    def completed_results(
        self,
        job_id: JobId,
    ) -> tuple[BiMetricExtractionResult, ...]:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT q.metric_id, q.period_id, a.answer_payload "
                        "FROM bi_questions q "
                        "JOIN bi_answers a ON a.question_id = q.question_id "
                        "WHERE q.materialization_job_id = %s "
                        "AND q.status = %s AND a.outcome = %s "
                        "ORDER BY q.metric_id, q.period_id",
                        (
                            job_id,
                            BiQuestionStatus.COMPLETED.value,
                            BiAnswerOutcome.COMPLETED.value,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as error:
            raise BiQuestionSnapshotRepositoryError(str(error)) from error

        results: list[BiMetricExtractionResult] = []
        try:
            for row in rows:
                result = BiMetricExtractionResult.model_validate(row["answer_payload"])
                if (
                    result.metric_id.value != row["metric_id"]
                    or result.period_id != row["period_id"]
                    or result.observation.period_id != result.period_id
                ):
                    raise BiQuestionSnapshotRepositoryError(
                        "answer payload identity does not match its question"
                    )
                results.append(result)
        except ValidationError as error:
            raise BiQuestionSnapshotRepositoryError(str(error)) from error
        return tuple(results)

    def latest_batch(
        self,
        company_id: CompanyId,
        workbook_hash: str,
    ) -> BiPersistedAnswerBatch | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "WITH latest_job AS ("
                        "SELECT materialization_job_id FROM bi_questions "
                        "WHERE company_id = %s AND workbook_hash = %s "
                        "ORDER BY updated_at DESC LIMIT 1"
                        ") SELECT q.question_id, q.materialization_job_id, "
                        "q.company_id, q.workbook_hash, q.index_id, q.metric_id, "
                        "q.period_id, q.question_version, q.question_text, q.status, "
                        "q.workflow_run_id, q.attempt_count, q.created_at, q.updated_at, "
                        "q.started_at, q.completed_at, a.answer_payload "
                        "FROM bi_questions q JOIN latest_job j USING (materialization_job_id) "
                        "LEFT JOIN bi_answers a ON a.question_id = q.question_id "
                        "AND q.status = %s AND a.outcome = %s "
                        "ORDER BY q.metric_id, q.period_id",
                        (
                            company_id,
                            workbook_hash,
                            BiQuestionStatus.COMPLETED.value,
                            BiAnswerOutcome.COMPLETED.value,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as error:
            raise BiQuestionSnapshotRepositoryError(str(error)) from error
        if not rows:
            return None

        question_columns = tuple(
            field_name
            for field_name in BiQuestionRecord.model_fields
        )
        try:
            questions = tuple(
                BiQuestionRecord.model_validate(
                    {name: row[name] for name in question_columns}
                )
                for row in rows
            )
            results = tuple(
                BiMetricExtractionResult.model_validate(row["answer_payload"])
                for row in rows
                if row["answer_payload"] is not None
            )
        except ValidationError as error:
            raise BiQuestionSnapshotRepositoryError(str(error)) from error
        identities = {
            (question.metric_id, question.period_id) for question in questions
        }
        if any(
            (result.metric_id, result.period_id) not in identities
            or result.observation.period_id != result.period_id
            for result in results
        ):
            raise BiQuestionSnapshotRepositoryError(
                "answer payload identity does not match its question"
            )
        return BiPersistedAnswerBatch(questions=questions, results=results)
