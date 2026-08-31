"""Move workbook semantic profiles to the data-sources domain.

Revision ID: 20260831_0006
Revises: 20260829_0005
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260831_0006"
down_revision: str | None = "20260829_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS workbook_profiles (
            profile_id VARCHAR(128) PRIMARY KEY,
            workbook_hash CHAR(64) NOT NULL
                REFERENCES source_files(file_id) ON DELETE CASCADE
                CHECK (workbook_hash ~ '^[a-f0-9]{64}$'),
            index_id VARCHAR(128) NOT NULL,
            profile_version VARCHAR(32) NOT NULL,
            status VARCHAR(16) NOT NULL CHECK (status IN ('ready', 'partial')),
            profile_payload JSONB NOT NULL CHECK (jsonb_typeof(profile_payload) = 'object'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (workbook_hash, index_id, profile_version)
        );

        CREATE INDEX IF NOT EXISTS idx_workbook_profiles_source
            ON workbook_profiles(workbook_hash, index_id, updated_at DESC);

        DROP TABLE IF EXISTS bi_document_profiles;
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS bi_document_profiles (
            company_id VARCHAR(128) NOT NULL,
            workbook_hash CHAR(64) NOT NULL
                CHECK (workbook_hash ~ '^[a-f0-9]{64}$'),
            index_id VARCHAR(128) NOT NULL,
            profile_version VARCHAR(128) NOT NULL,
            profile_payload JSONB NOT NULL
                CHECK (jsonb_typeof(profile_payload) = 'object'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (company_id, workbook_hash, index_id, profile_version)
        );
        CREATE INDEX IF NOT EXISTS idx_bi_document_profiles_source
            ON bi_document_profiles(company_id, workbook_hash, index_id);
        DROP TABLE IF EXISTS workbook_profiles;
        """
    )
