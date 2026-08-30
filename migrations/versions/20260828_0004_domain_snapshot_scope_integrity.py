"""Bind snapshot heads to the same domain and scope.

Revision ID: 20260828_0004
Revises: 20260828_0003
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260828_0004"
down_revision: str | None = "20260828_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        "ALTER TABLE domain_snapshots "
        "ADD CONSTRAINT uq_domain_snapshots_scoped_identity "
        "UNIQUE (domain, scope_key, snapshot_id)"
    )
    connection.exec_driver_sql(
        "ALTER TABLE domain_snapshot_heads "
        "DROP CONSTRAINT domain_snapshot_heads_current_snapshot_id_fkey"
    )
    connection.exec_driver_sql(
        "ALTER TABLE domain_snapshot_heads "
        "ADD CONSTRAINT fk_domain_snapshot_heads_scoped_snapshot "
        "FOREIGN KEY (domain, scope_key, current_snapshot_id) "
        "REFERENCES domain_snapshots(domain, scope_key, snapshot_id)"
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        "ALTER TABLE domain_snapshot_heads DROP CONSTRAINT fk_domain_snapshot_heads_scoped_snapshot"
    )
    connection.exec_driver_sql(
        "ALTER TABLE domain_snapshot_heads "
        "ADD CONSTRAINT domain_snapshot_heads_current_snapshot_id_fkey "
        "FOREIGN KEY (current_snapshot_id) REFERENCES domain_snapshots(snapshot_id)"
    )
    connection.exec_driver_sql(
        "ALTER TABLE domain_snapshots DROP CONSTRAINT uq_domain_snapshots_scoped_identity"
    )
