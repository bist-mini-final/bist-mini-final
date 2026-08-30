"""Add durable queues for distributed Excel ingestion shards.

Revision ID: 20260829_0005
Revises: 20260828_0004
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260829_0005"
down_revision: str | None = "20260828_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS ingestion_shards (
            operation_id VARCHAR(128) NOT NULL,
            phase VARCHAR(32) NOT NULL
                CHECK (phase IN ('embedding', 'vector_copy')),
            shard_index INT NOT NULL CHECK (shard_index >= 0),
            status VARCHAR(32) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            payload JSONB NOT NULL,
            worker_id VARCHAR(128),
            lease_token VARCHAR(64),
            attempt_count INT NOT NULL DEFAULT 0,
            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            claimed_at TIMESTAMPTZ,
            heartbeat_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            total_tokens BIGINT,
            duration_seconds DOUBLE PRECISION,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (operation_id, phase, shard_index)
        );

        CREATE INDEX IF NOT EXISTS idx_ingestion_shards_claim
            ON ingestion_shards(phase, status, available_at, created_at)
            WHERE status IN ('queued', 'running');
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("DROP TABLE IF EXISTS ingestion_shards")
