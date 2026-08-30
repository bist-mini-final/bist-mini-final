from dataclasses import dataclass
from typing import Final

import psycopg2

from backend.core.settings import PGVECTOR_URL
from backend.storage.audit_schema import AUDIT_SCHEMA_SQL, BI_COMPANY_AUDIT_SQL
from backend.storage.connection_pool import get_pooled_raw_connection

BI_SCHEMA_SQL: Final = (
    """
CREATE TABLE IF NOT EXISTS bi_companies (
    company_id VARCHAR(128) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    current_snapshot_id VARCHAR(128),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE bi_companies ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bi_companies ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS bi_materialization_jobs (
    job_id VARCHAR(128) PRIMARY KEY,
    company_id VARCHAR(128) NOT NULL REFERENCES bi_companies(company_id),
    workbook_hash CHAR(64) NOT NULL CHECK (workbook_hash ~ '^[a-f0-9]{64}$'),
    request_payload JSONB NOT NULL CHECK (jsonb_typeof(request_payload) = 'object'),
    status VARCHAR(32) NOT NULL CHECK (
        status IN ('queued', 'indexing', 'profiling', 'extracting',
                   'materializing', 'ready', 'partial', 'failed')
    ),
    completed_requests INTEGER NOT NULL DEFAULT 0 CHECK (completed_requests >= 0),
    total_requests INTEGER NOT NULL DEFAULT 0 CHECK (total_requests >= 0),
    published_snapshot_id VARCHAR(128),
    error_code VARCHAR(128),
    message VARCHAR(500),
    worker_id VARCHAR(128),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    heartbeat_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bi_dashboard_snapshots (
    snapshot_id VARCHAR(128) PRIMARY KEY,
    company_id VARCHAR(128) NOT NULL REFERENCES bi_companies(company_id),
    workbook_hash CHAR(64) NOT NULL CHECK (workbook_hash ~ '^[a-f0-9]{64}$'),
    snapshot_payload JSONB NOT NULL CHECK (jsonb_typeof(snapshot_payload) = 'object'),
    generated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bi_questions (
    question_id VARCHAR(128) PRIMARY KEY,
    materialization_job_id VARCHAR(128) NOT NULL,
    company_id VARCHAR(128) NOT NULL,
    workbook_hash CHAR(64) NOT NULL CHECK (workbook_hash ~ '^[a-f0-9]{64}$'),
    index_id VARCHAR(128) NOT NULL,
    metric_id VARCHAR(64) NOT NULL,
    period_id VARCHAR(128) NOT NULL,
    question_version VARCHAR(128) NOT NULL,
    question_text TEXT NOT NULL CHECK (char_length(question_text) BETWEEN 1 AND 2000),
    status VARCHAR(16) NOT NULL CHECK (
        status IN ('queued', 'running', 'completed', 'failed')
    ),
    workflow_run_id VARCHAR(64) UNIQUE,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (materialization_job_id, metric_id, period_id, question_version),
    CHECK (
        (status = 'queued' AND started_at IS NULL AND completed_at IS NULL)
        OR (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL)
        OR (
            status IN ('completed', 'failed')
            AND started_at IS NOT NULL
            AND completed_at IS NOT NULL
        )
    )
);

CREATE TABLE IF NOT EXISTS bi_answers (
    answer_id VARCHAR(128) PRIMARY KEY,
    question_id VARCHAR(128) NOT NULL UNIQUE
        REFERENCES bi_questions(question_id) ON DELETE CASCADE,
    outcome VARCHAR(16) NOT NULL CHECK (outcome IN ('completed', 'failed')),
    answer_text TEXT,
    answer_payload JSONB,
    evidence_cell_ids JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(evidence_cell_ids) = 'array'
    ),
    error_code VARCHAR(128),
    error_message TEXT,
    model_name VARCHAR(128),
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    prompt_tokens INTEGER CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER CHECK (completion_tokens >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (
            outcome = 'completed'
            AND answer_text IS NOT NULL
            AND answer_payload IS NOT NULL
            AND error_code IS NULL
            AND error_message IS NULL
        )
        OR (
            outcome = 'failed'
            AND answer_text IS NULL
            AND answer_payload IS NULL
            AND evidence_cell_ids = '[]'::jsonb
            AND error_code IS NOT NULL
            AND error_message IS NOT NULL
        )
    )
);

CREATE TABLE IF NOT EXISTS bi_document_profiles (
    company_id VARCHAR(128) NOT NULL,
    workbook_hash CHAR(64) NOT NULL CHECK (workbook_hash ~ '^[a-f0-9]{64}$'),
    index_id VARCHAR(128) NOT NULL,
    profile_version VARCHAR(128) NOT NULL,
    profile_payload JSONB NOT NULL CHECK (
        jsonb_typeof(profile_payload) = 'object'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, workbook_hash, index_id, profile_version)
);

CREATE INDEX IF NOT EXISTS idx_bi_questions_job
    ON bi_questions(materialization_job_id);
CREATE INDEX IF NOT EXISTS idx_bi_questions_company_source
    ON bi_questions(company_id, workbook_hash, index_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_bi_questions_status
    ON bi_questions(status, created_at);
CREATE INDEX IF NOT EXISTS idx_bi_document_profiles_source
    ON bi_document_profiles(company_id, workbook_hash, index_id);
CREATE INDEX IF NOT EXISTS idx_bi_materialization_queue
    ON bi_materialization_jobs(status, available_at, updated_at);
CREATE INDEX IF NOT EXISTS idx_bi_materialization_company
    ON bi_materialization_jobs(company_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_bi_snapshots_company
    ON bi_dashboard_snapshots(company_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_bi_companies_active
    ON bi_companies(display_name, company_id) WHERE is_deleted = FALSE;
"""
    + AUDIT_SCHEMA_SQL
    + BI_COMPANY_AUDIT_SQL
)

BI_SCHEMA_LOCK_KEY: Final = "bist:bi-schema:v1"


@dataclass(frozen=True, slots=True)
class BiDatabaseUnavailableError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"BI database is unavailable: {self.reason}"


@dataclass(frozen=True, slots=True)
class BiSchemaInitializationError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"BI schema initialization failed: {self.reason}"


def ensure_bi_schema(database_url: str = PGVECTOR_URL) -> None:
    try:
        with get_pooled_raw_connection(database_url) as connection:
            with connection.cursor() as cursor:
                # Kubernetes can start several short-lived workers at once.  DDL
                # such as CREATE INDEX IF NOT EXISTS is individually idempotent,
                # but concurrent schema transactions can still deadlock while
                # taking relation locks in different orders.  Serialize only the
                # schema bootstrap transaction; normal queue work stays parallel.
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s));",
                    (BI_SCHEMA_LOCK_KEY,),
                )
                cursor.execute(BI_SCHEMA_SQL)
            connection.commit()
    except psycopg2.OperationalError as error:
        raise BiDatabaseUnavailableError(reason=str(error)) from error
    except psycopg2.Error as error:
        raise BiSchemaInitializationError(reason=str(error)) from error
