"""Add reusable immutable domain snapshot storage.

Revision ID: 20260828_0003
Revises: 20260828_0002
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260828_0003"
down_revision: str | None = "20260828_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS domain_snapshots (
            snapshot_id VARCHAR(128) PRIMARY KEY,
            domain VARCHAR(64) NOT NULL,
            scope_key VARCHAR(128) NOT NULL,
            schema_version INTEGER NOT NULL CHECK (schema_version > 0),
            source_fingerprint CHAR(64) NOT NULL
                CHECK (source_fingerprint ~ '^[a-f0-9]{64}$'),
            snapshot_payload JSONB NOT NULL
                CHECK (jsonb_typeof(snapshot_payload) = 'object'),
            generated_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS domain_snapshot_heads (
            domain VARCHAR(64) NOT NULL,
            scope_key VARCHAR(128) NOT NULL,
            current_snapshot_id VARCHAR(128) NOT NULL
                REFERENCES domain_snapshots(snapshot_id),
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (domain, scope_key)
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_domain_snapshots_history "
        "ON domain_snapshots(domain, scope_key, generated_at DESC)"
    )


def downgrade() -> None:
    raise RuntimeError(
        "The domain snapshot downgrade is disabled because it would erase snapshot history."
    )
