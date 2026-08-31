"""Adopt the existing PostgreSQL, BI, and benchmark schema without data loss.

Revision ID: 20260827_0001
Revises:
Create Date: 2026-08-27
"""

from collections.abc import Sequence

from alembic import op

from backend.domains.benchmark.infrastructure.postgres import BENCHMARK_SCHEMA_SQL
from backend.domains.bi.infrastructure.postgres import BI_SCHEMA_SQL
from backend.domains.chatbot.infrastructure.postgres import CHATBOT_SCHEMA_SQL
from backend.domains.data_sources.infrastructure.postgres import DATA_SOURCE_SCHEMA_SQL
from backend.domains.workflow.infrastructure.postgres import WORKFLOW_SCHEMA_SQL

revision: str = "20260827_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create missing objects and adopt existing installations in place."""

    connection = op.get_bind()
    connection.exec_driver_sql(DATA_SOURCE_SCHEMA_SQL)
    connection.exec_driver_sql(WORKFLOW_SCHEMA_SQL)
    connection.exec_driver_sql(CHATBOT_SCHEMA_SQL)
    connection.exec_driver_sql(BI_SCHEMA_SQL)
    connection.exec_driver_sql(BENCHMARK_SCHEMA_SQL)


def downgrade() -> None:
    """Protect application data from an accidental baseline downgrade."""

    raise RuntimeError(
        "The baseline downgrade is intentionally disabled because it would drop user data."
    )
