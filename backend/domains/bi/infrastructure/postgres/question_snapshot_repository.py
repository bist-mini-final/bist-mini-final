"""PostgreSQL BI question snapshot repository."""


import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import ValidationError

from backend.core.settings import PGVECTOR_URL
from backend.domains.bi.application.errors import BiQuestionSnapshotRepositoryError
from backend.domains.bi.domain.catalog import CATALOG_VERSION
from backend.domains.bi.domain.extraction_models import BiMetricExtractionResult
from backend.domains.bi.domain.models import JobId
from backend.domains.bi.domain.question_records import BiAnswerOutcome, BiQuestionStatus
from backend.platform.postgres.pool import get_pooled_raw_connection


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
                        "SELECT DISTINCT ON (q.metric_id, q.period_id) "
                        "q.metric_id, q.period_id, a.answer_payload "
                        "FROM bi_questions q "
                        "JOIN bi_answers a ON a.question_id = q.question_id "
                        "WHERE q.materialization_job_id = %s "
                        "AND q.question_version = %s "
                        "AND q.status = %s AND a.outcome = %s "
                        "ORDER BY q.metric_id, q.period_id, a.created_at DESC",
                        (
                            job_id,
                            CATALOG_VERSION,
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
