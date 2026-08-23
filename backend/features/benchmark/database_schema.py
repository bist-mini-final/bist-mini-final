from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import psycopg2

from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection

BENCHMARK_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS benchmark_jobs (
    job_id VARCHAR(128) PRIMARY KEY,
    request_payload JSONB NOT NULL CHECK (jsonb_typeof(request_payload) = 'object'),
    status VARCHAR(16) NOT NULL CHECK (
        status IN ('queued', 'running', 'pausing', 'paused', 'cancelling',
                   'completed', 'cancelled', 'failed')
    ),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed >= 0),
    total INTEGER NOT NULL CHECK (total >= 1),
    current_payload JSONB,
    active_run_id VARCHAR(64),
    last_run_payload JSONB,
    logs JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(logs) = 'array'),
    result_payload JSONB,
    error TEXT,
    pause_requested BOOLEAN NOT NULL DEFAULT FALSE,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    worker_id VARCHAR(128),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS benchmark_result_rows (
    job_id VARCHAR(128) NOT NULL
        REFERENCES benchmark_jobs(job_id) ON DELETE CASCADE,
    workflow_id VARCHAR(128) NOT NULL,
    case_id VARCHAR(128) NOT NULL,
    row_payload JSONB NOT NULL CHECK (jsonb_typeof(row_payload) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, workflow_id, case_id)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_jobs_queue
    ON benchmark_jobs(status, available_at, updated_at);
CREATE INDEX IF NOT EXISTS idx_benchmark_jobs_results
    ON benchmark_jobs(updated_at DESC)
    WHERE status = 'completed';
CREATE INDEX IF NOT EXISTS idx_benchmark_result_rows_job
    ON benchmark_result_rows(job_id, created_at);
"""


@dataclass(frozen=True, slots=True)
class BenchmarkSchemaError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"benchmark schema initialization failed: {self.reason}"


def ensure_benchmark_schema(database_url: str = PGVECTOR_URL) -> None:
    try:
        with get_pooled_raw_connection(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(BENCHMARK_SCHEMA_SQL)
            connection.commit()
    except psycopg2.Error as error:
        raise BenchmarkSchemaError(str(error)) from error


__all__ = ["BENCHMARK_SCHEMA_SQL", "BenchmarkSchemaError", "ensure_benchmark_schema"]
