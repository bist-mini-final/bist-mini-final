"""Durable PostgreSQL queue used by distributed Excel-ingestion shard Jobs."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

import psycopg2.extras

from backend.core.settings import PGVECTOR_URL
from backend.domains.data_sources.domain import (
    IngestionShard,
    IngestionShardLeaseLost,
    IngestionShardPhase,
    IngestionShardPhaseSnapshot,
)
from backend.platform.postgres.pool import get_pooled_raw_connection


class PostgresIngestionShardRepository:
    """Own shard creation, lease transitions, progress snapshots, and retries."""

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self.database_url = database_url

    def _connection(self) -> Any:
        url = self.database_url.replace("postgresql+psycopg://", "postgresql://")
        return get_pooled_raw_connection(url)

    @contextmanager
    def operation_lock(self, operation_id: str, purpose: str) -> Iterator[None]:
        """Serialize parent-only artifact assembly/cleanup across processes."""

        lock_key = f"ingestion:{operation_id}:{purpose}"
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_lock(hashtextextended(%s, 0));",
                    (lock_key,),
                )
            try:
                yield
            finally:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s, 0));",
                        (lock_key,),
                    )
                connection.commit()
        finally:
            connection.close()

    def prepare_phase(
        self,
        operation_id: str,
        phase: IngestionShardPhase,
        payloads: Sequence[Mapping[str, Any]],
    ) -> None:
        """Insert a deterministic shard set without resetting completed work."""

        if not payloads:
            raise ValueError("ingestion shard phase requires at least one payload")
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s));",
                    (f"{operation_id}:{phase}",),
                )
                for shard_index, payload in enumerate(payloads):
                    cursor.execute(
                        """
                        INSERT INTO ingestion_shards (
                            operation_id, phase, shard_index, status, payload
                        ) VALUES (%s, %s, %s, 'queued', %s)
                        ON CONFLICT (operation_id, phase, shard_index) DO UPDATE
                        SET payload = EXCLUDED.payload,
                            status = CASE
                                WHEN ingestion_shards.status = 'failed' THEN 'queued'
                                ELSE ingestion_shards.status
                            END,
                            available_at = CASE
                                WHEN ingestion_shards.status = 'failed' THEN NOW()
                                ELSE ingestion_shards.available_at
                            END,
                            attempt_count = CASE
                                WHEN ingestion_shards.status = 'failed' THEN 0
                                ELSE ingestion_shards.attempt_count
                            END,
                            error_message = CASE
                                WHEN ingestion_shards.status = 'failed' THEN NULL
                                ELSE ingestion_shards.error_message
                            END,
                            updated_at = NOW();
                        """,
                        (
                            operation_id,
                            phase,
                            shard_index,
                            psycopg2.extras.Json(dict(payload)),
                        ),
                    )
                cursor.execute(
                    """
                    DELETE FROM ingestion_shards
                    WHERE operation_id = %s
                      AND phase = %s
                      AND shard_index >= %s
                      AND status <> 'running';
                    """,
                    (operation_id, phase, len(payloads)),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def requeue_shards(
        self,
        operation_id: str,
        phase: IngestionShardPhase,
        shard_indexes: Sequence[int],
    ) -> int:
        """Reset successful metadata when its corresponding artifact is missing."""

        if not shard_indexes:
            return 0
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingestion_shards
                    SET status = 'queued',
                        worker_id = NULL,
                        lease_token = NULL,
                        available_at = NOW(),
                        claimed_at = NULL,
                        heartbeat_at = NULL,
                        completed_at = NULL,
                        total_tokens = NULL,
                        duration_seconds = NULL,
                        error_message = NULL,
                        updated_at = NOW()
                    WHERE operation_id = %s
                      AND phase = %s
                      AND shard_index = ANY(%s::int[])
                      AND status <> 'running';
                    """,
                    (operation_id, phase, list(shard_indexes)),
                )
                changed = cursor.rowcount
            connection.commit()
            return changed
        finally:
            connection.close()

    def claim_next(
        self,
        phase: IngestionShardPhase,
        worker_id: str,
        *,
        stale_after_seconds: int = 180,
    ) -> IngestionShard | None:
        """Atomically claim one queued or stale shard using SKIP LOCKED."""

        lease_token = uuid4().hex
        connection = self._connection()
        try:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT operation_id, phase, shard_index
                        FROM ingestion_shards
                        WHERE phase = %s
                          AND (
                              (status = 'queued' AND available_at <= NOW())
                              OR (
                                  status = 'running'
                                  AND (
                                      heartbeat_at IS NULL
                                      OR heartbeat_at < NOW() - (%s * INTERVAL '1 second')
                                  )
                              )
                          )
                        ORDER BY available_at, created_at, operation_id, shard_index
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE ingestion_shards AS shard
                    SET status = 'running',
                        worker_id = %s,
                        lease_token = %s,
                        attempt_count = attempt_count + 1,
                        claimed_at = NOW(),
                        heartbeat_at = NOW(),
                        completed_at = NULL,
                        error_message = NULL,
                        updated_at = NOW()
                    FROM candidate
                    WHERE shard.operation_id = candidate.operation_id
                      AND shard.phase = candidate.phase
                      AND shard.shard_index = candidate.shard_index
                    RETURNING shard.operation_id, shard.phase, shard.shard_index,
                              shard.status, shard.payload, shard.worker_id,
                              shard.lease_token, shard.attempt_count,
                              shard.total_tokens, shard.duration_seconds,
                              shard.error_message;
                    """,
                    (phase, stale_after_seconds, worker_id, lease_token),
                )
                row = cursor.fetchone()
            connection.commit()
        finally:
            connection.close()
        return IngestionShard.model_validate(dict(row)) if row else None

    def heartbeat(self, shard: IngestionShard) -> bool:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingestion_shards
                    SET heartbeat_at = NOW(), updated_at = NOW()
                    WHERE operation_id = %s
                      AND phase = %s
                      AND shard_index = %s
                      AND worker_id = %s
                      AND lease_token = %s
                      AND status = 'running';
                    """,
                    (
                        shard.operation_id,
                        shard.phase,
                        shard.shard_index,
                        shard.worker_id,
                        shard.lease_token,
                    ),
                )
                renewed = cursor.rowcount == 1
            connection.commit()
            return renewed
        finally:
            connection.close()

    def complete(
        self,
        shard: IngestionShard,
        *,
        total_tokens: int = 0,
        duration_seconds: float,
    ) -> None:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingestion_shards
                    SET status = 'succeeded',
                        total_tokens = %s,
                        duration_seconds = %s,
                        completed_at = NOW(),
                        heartbeat_at = NOW(),
                        updated_at = NOW()
                    WHERE operation_id = %s
                      AND phase = %s
                      AND shard_index = %s
                      AND worker_id = %s
                      AND lease_token = %s
                      AND status = 'running';
                    """,
                    (
                        total_tokens,
                        duration_seconds,
                        shard.operation_id,
                        shard.phase,
                        shard.shard_index,
                        shard.worker_id,
                        shard.lease_token,
                    ),
                )
                completed = cursor.rowcount == 1
            connection.commit()
        finally:
            connection.close()
        if not completed:
            raise IngestionShardLeaseLost(
                f"ingestion shard lease lost: {shard.operation_id}/{shard.phase}/{shard.shard_index}"
            )

    def fail(
        self,
        shard: IngestionShard,
        error: str,
        *,
        max_attempts: int = 3,
        retry_delay_seconds: int = 5,
    ) -> bool:
        """Record failure and return whether the shard was requeued."""

        message = error[:2000]
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingestion_shards
                    SET status = CASE
                            WHEN attempt_count < %s THEN 'queued'
                            ELSE 'failed'
                        END,
                        worker_id = NULL,
                        lease_token = NULL,
                        available_at = CASE
                            WHEN attempt_count < %s
                            THEN NOW() + (%s * INTERVAL '1 second')
                            ELSE available_at
                        END,
                        heartbeat_at = NULL,
                        completed_at = CASE
                            WHEN attempt_count < %s THEN NULL
                            ELSE NOW()
                        END,
                        error_message = %s,
                        updated_at = NOW()
                    WHERE operation_id = %s
                      AND phase = %s
                      AND shard_index = %s
                      AND worker_id = %s
                      AND lease_token = %s
                      AND status = 'running'
                    RETURNING status;
                    """,
                    (
                        max_attempts,
                        max_attempts,
                        retry_delay_seconds,
                        max_attempts,
                        message,
                        shard.operation_id,
                        shard.phase,
                        shard.shard_index,
                        shard.worker_id,
                        shard.lease_token,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        finally:
            connection.close()
        if row is None:
            raise IngestionShardLeaseLost(
                f"ingestion shard lease lost: {shard.operation_id}/{shard.phase}/{shard.shard_index}"
            )
        return str(row[0]) == "queued"

    def phase_snapshot(
        self,
        operation_id: str,
        phase: IngestionShardPhase,
    ) -> IngestionShardPhaseSnapshot:
        connection = self._connection()
        try:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT operation_id, phase, shard_index, status, payload,
                           worker_id, lease_token, attempt_count, total_tokens,
                           duration_seconds, error_message
                    FROM ingestion_shards
                    WHERE operation_id = %s AND phase = %s
                    ORDER BY shard_index;
                    """,
                    (operation_id, phase),
                )
                rows = cursor.fetchall()
        finally:
            connection.close()
        return IngestionShardPhaseSnapshot(
            tuple(IngestionShard.model_validate(dict(row)) for row in rows)
        )


__all__ = [
    "IngestionShard",
    "IngestionShardLeaseLost",
    "IngestionShardPhase",
    "IngestionShardPhaseSnapshot",
    "PostgresIngestionShardRepository",
]
