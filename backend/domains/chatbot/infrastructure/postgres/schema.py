"""PostgreSQL schema owned by the chatbot domain."""

from typing import Final

CHATBOT_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    client_id VARCHAR(128) NOT NULL,
    title VARCHAR(160) NOT NULL DEFAULT '새 대화',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
    workflow_run_id VARCHAR(64),
    visualization JSONB,
    evidence JSONB NOT NULL DEFAULT '[]',
    attachments JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS visualization JSONB;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '[]';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
UPDATE chat_messages SET completed_at = created_at
    WHERE role = 'assistant' AND status IN ('completed', 'failed') AND completed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_client ON chat_sessions(client_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_run
    ON chat_messages(workflow_run_id) WHERE workflow_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS chat_attachments (
    attachment_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128),
    file_size BIGINT NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    extracted_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_attachments_session
    ON chat_attachments(session_id, created_at);

CREATE TABLE IF NOT EXISTS chat_suggested_questions (
    suggestion_date DATE NOT NULL,
    position SMALLINT NOT NULL,
    question VARCHAR(300) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (suggestion_date, position)
);
"""

__all__ = ["CHATBOT_SCHEMA_SQL"]
