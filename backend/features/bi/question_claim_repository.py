from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection

from .question_records import (
    BiQuestionClaim,
    BiQuestionRecord,
    BiQuestionStatus,
)
from .question_repository_queries import BiQuestionRepositoryError


@dataclass(frozen=True, slots=True)
class PostgresBiQuestionClaimer:
    database_url: str = PGVECTOR_URL

    def claim_next(
        self,
        command: BiQuestionClaim,
    ) -> BiQuestionRecord | None:
        try:
            with get_pooled_raw_connection(self.database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "WITH candidate AS ("
                        "SELECT question_id FROM bi_questions "
                        "WHERE status = %s "
                        "ORDER BY created_at, question_id "
                        "FOR UPDATE SKIP LOCKED LIMIT 1"
                        ") UPDATE bi_questions AS question "
                        "SET status = %s, workflow_run_id = %s, "
                        "attempt_count = attempt_count + 1, "
                        "started_at = %s, completed_at = NULL, updated_at = %s "
                        "FROM candidate "
                        "WHERE question.question_id = candidate.question_id "
                        "RETURNING question.*",
                        (
                            BiQuestionStatus.QUEUED.value,
                            BiQuestionStatus.RUNNING.value,
                            command.workflow_run_id,
                            command.claimed_at,
                            command.claimed_at,
                        ),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="claim_next",
                reason=str(error),
            ) from error
        return BiQuestionRecord.model_validate(row) if row is not None else None
