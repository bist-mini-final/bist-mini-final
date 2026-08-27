"""Adopt the existing PostgreSQL, BI, and benchmark schema without data loss.

Revision ID: 20260827_0001
Revises:
Create Date: 2026-08-27
"""

from collections.abc import Sequence

from alembic import op

from backend.features.benchmark.database_schema import BENCHMARK_SCHEMA_SQL
from backend.features.bi.database_schema import BI_SCHEMA_SQL
from backend.storage.db_manager import DDL_INIT

revision: str = "20260827_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create missing objects and adopt existing installations in place."""

    connection = op.get_bind()
    connection.exec_driver_sql(DDL_INIT)
    connection.exec_driver_sql(BI_SCHEMA_SQL)
    connection.exec_driver_sql(BENCHMARK_SCHEMA_SQL)


def downgrade() -> None:
    """Protect application data from an accidental baseline downgrade."""

    raise RuntimeError(
        "The baseline downgrade is intentionally disabled because it would drop user data."
    )
