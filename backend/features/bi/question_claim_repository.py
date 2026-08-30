import uuid
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.core.settings import PGVECTOR_URL
from backend.domains.bi.domain.question_records import (
    BiQuestionClaim,
    BiQuestionRecord,
    BiQuestionStatus,
)
from backend.storage.connection_pool import get_pooled_raw_connection

from .question_repository_queries import BiQuestionRepositoryError


@dataclass(frozen=True, slots=True)
class PostgresBiQuestionClaimer:
    database_url: str = PGVECTOR_URL

    def claim_next(
        self,
        command: BiQuestionClaim,
    ) -> BiQuestionRecord | None:
        results = self.claim_next_batch(command, batch_size=1)
        return results[0] if results else None

    def claim_next_batch(
        self,
        command: BiQuestionClaim,
        batch_size: int = 16,
    ) -> tuple[BiQuestionRecord, ...]:
        """Atomically claim up to *batch_size* queued (or stale-running) questions.

        PostgreSQL does not allow FOR UPDATE with window functions in the same
        query block.  We work around this with two CTE steps:

        1. ``locked``   - SELECT FOR UPDATE SKIP LOCKED to atomically reserve N
                          question_ids without window functions.
        2. ``numbered`` - Apply ROW_NUMBER() to the already-locked IDs so each
                          row gets a unique ``workflow_run_id`` suffix.

        This satisfies the UNIQUE constraint on ``workflow_run_id`` while keeping
        all N claims within one transaction.
        """
        base_id = f"{command.workflow_run_id}-{uuid.uuid4().hex[:8]}"
        try:
            with get_pooled_raw_connection(self.database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        # Step 1: lock N candidates (no window fn here)
                        "WITH locked AS ("
                        "  SELECT question_id FROM bi_questions"
                        "  WHERE status = %s OR (status = %s AND"
                        "    updated_at < %s - (180 * INTERVAL '1 second'))"
                        "  ORDER BY created_at, question_id"
                        "  FOR UPDATE SKIP LOCKED LIMIT %s"
                        # Step 2: assign a row number to each locked id
                        "), numbered AS ("
                        "  SELECT question_id,"
                        "    ROW_NUMBER() OVER (ORDER BY question_id) AS rn"
                        "  FROM locked"
                        # Step 3: update using the unique suffix
                        ") UPDATE bi_questions AS question"
                        "  SET status = %s,"
                        "    workflow_run_id = %s || '-' || numbered.rn,"
                        "    attempt_count = attempt_count + 1,"
                        "    started_at = %s, completed_at = NULL, updated_at = %s"
                        "  FROM numbered"
                        "  WHERE question.question_id = numbered.question_id"
                        "  RETURNING question.*",
                        (
                            BiQuestionStatus.QUEUED.value,
                            BiQuestionStatus.RUNNING.value,
                            command.claimed_at,
                            batch_size,
                            BiQuestionStatus.RUNNING.value,
                            base_id,
                            command.claimed_at,
                            command.claimed_at,
                        ),
                    )
                    rows = cursor.fetchall()
                connection.commit()
        except psycopg2.Error as error:
            raise BiQuestionRepositoryError(
                operation="claim_next_batch",
                reason=str(error),
            ) from error
        return tuple(BiQuestionRecord.model_validate(row) for row in rows)


