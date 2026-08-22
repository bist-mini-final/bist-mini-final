from dataclasses import dataclass
from typing import Final

import psycopg2

from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


BI_SCHEMA_SQL: Final = """
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
"""


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
                cursor.execute(BI_SCHEMA_SQL)
            connection.commit()
    except psycopg2.OperationalError as error:
        raise BiDatabaseUnavailableError(reason=str(error)) from error
    except psycopg2.Error as error:
        raise BiSchemaInitializationError(reason=str(error)) from error
