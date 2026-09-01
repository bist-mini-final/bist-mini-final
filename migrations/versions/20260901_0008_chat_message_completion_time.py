"""Persist the timestamp at which an assistant response becomes available.

Revision ID: 20260901_0008
Revises: 20260831_0007
Create Date: 2026-09-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260901_0008"
down_revision: str | None = "20260831_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chat_messages "
        "ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"
    )
    op.execute(
        "UPDATE chat_messages SET completed_at = created_at "
        "WHERE role = 'assistant' AND status IN ('completed', 'failed') "
        "AND completed_at IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS completed_at")
