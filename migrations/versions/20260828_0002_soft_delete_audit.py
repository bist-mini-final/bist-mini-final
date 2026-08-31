"""Add recoverable deletion and append-only entity audit history.

Revision ID: 20260828_0002
Revises: 20260827_0001
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op

from backend.platform.postgres.audit_schema import (
    AUDIT_SCHEMA_SQL,
    BI_COMPANY_AUDIT_SQL,
    SOURCE_FILE_AUDIT_SQL,
)

revision: str = "20260828_0002"
down_revision: str | None = "20260827_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        "ALTER TABLE source_files ADD COLUMN IF NOT EXISTS "
        "is_deleted BOOLEAN NOT NULL DEFAULT FALSE"
    )
    connection.exec_driver_sql(
        "ALTER TABLE source_files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
    )
    connection.exec_driver_sql(
        "ALTER TABLE bi_companies ADD COLUMN IF NOT EXISTS "
        "is_deleted BOOLEAN NOT NULL DEFAULT FALSE"
    )
    connection.exec_driver_sql(
        "ALTER TABLE bi_companies ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_source_files_active "
        "ON source_files(created_at DESC) WHERE is_deleted = FALSE"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_bi_companies_active "
        "ON bi_companies(display_name, company_id) WHERE is_deleted = FALSE"
    )
    connection.exec_driver_sql(AUDIT_SCHEMA_SQL)
    connection.exec_driver_sql(SOURCE_FILE_AUDIT_SQL)
    connection.exec_driver_sql(BI_COMPANY_AUDIT_SQL)


def downgrade() -> None:
    raise RuntimeError(
        "The soft-delete/audit downgrade is disabled because it would erase audit history."
    )
