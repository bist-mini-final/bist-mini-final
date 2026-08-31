"""PostgreSQL schema owned by the data-sources domain."""

from typing import Final

from backend.platform.postgres.audit_schema import AUDIT_SCHEMA_SQL, SOURCE_FILE_AUDIT_SQL

DATA_SOURCE_SCHEMA_SQL: Final = (
    """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS source_files (
    file_id VARCHAR(64) PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_size BIGINT NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE source_files ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE source_files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS sheets (
    sheet_id VARCHAR(128) PRIMARY KEY,
    file_id VARCHAR(64) REFERENCES source_files(file_id) ON DELETE CASCADE,
    sheet_name VARCHAR(128) NOT NULL,
    sheet_index INT NOT NULL,
    is_visible BOOLEAN DEFAULT TRUE,
    row_count INT NOT NULL DEFAULT 0,
    column_count INT NOT NULL DEFAULT 0,
    detected_tables JSONB DEFAULT '[]',
    parsed_at TIMESTAMPTZ DEFAULT NOW()
);

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

CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL UNIQUE,
    cmetadata JSON
);
CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id VARCHAR PRIMARY KEY,
    collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding vector,
    document VARCHAR,
    cmetadata JSONB
);

CREATE TABLE IF NOT EXISTS ingestion_shards (
    operation_id VARCHAR(128) NOT NULL,
    phase VARCHAR(32) NOT NULL CHECK (phase IN ('embedding', 'vector_copy')),
    shard_index INT NOT NULL CHECK (shard_index >= 0),
    status VARCHAR(32) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    payload JSONB NOT NULL,
    worker_id VARCHAR(128),
    lease_token VARCHAR(64),
    attempt_count INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    total_tokens BIGINT,
    duration_seconds DOUBLE PRECISION,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (operation_id, phase, shard_index)
);

CREATE INDEX IF NOT EXISTS idx_source_files_hash ON source_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_source_files_active
    ON source_files(created_at DESC) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_sheets_file_id ON sheets(file_id);
CREATE INDEX IF NOT EXISTS idx_workbook_profiles_source
    ON workbook_profiles(workbook_hash, index_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_langchain_cmetadata_gin
    ON langchain_pg_embedding USING gin (cmetadata jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_ingestion_shards_claim
    ON ingestion_shards(phase, status, available_at, created_at)
    WHERE status IN ('queued', 'running');
"""
    + AUDIT_SCHEMA_SQL
    + SOURCE_FILE_AUDIT_SQL
)

__all__ = ["DATA_SOURCE_SCHEMA_SQL"]
