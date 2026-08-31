"""PostgreSQL schema owned by the workflow domain."""

from typing import Final

WORKFLOW_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    workflow_id VARCHAR(64) NOT NULL,
    workflow_updated_at VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    schema_version INT NOT NULL DEFAULT 2,
    graph JSONB NOT NULL DEFAULT '{}',
    runtime_inputs JSONB NOT NULL DEFAULT '{}',
    use_cache BOOLEAN DEFAULT TRUE,
    orchestration JSONB NOT NULL DEFAULT '{}',
    queue_name VARCHAR(64),
    worker_id VARCHAR(128),
    lease_token VARCHAR(64),
    priority INT NOT NULL DEFAULT 0,
    attempt_count INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    batches JSONB NOT NULL DEFAULT '[]',
    nodes JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS orchestration JSONB NOT NULL DEFAULT '{}';
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS queue_name VARCHAR(64);
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(128);
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS lease_token VARCHAR(64);
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS node_execution_logs (
    log_id VARCHAR(128) PRIMARY KEY,
    run_id VARCHAR(64) REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    node_id VARCHAR(128) NOT NULL,
    module_type VARCHAR(64) NOT NULL,
    batch_index INT DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    input_payload JSONB,
    config_payload JSONB DEFAULT '{}',
    output JSONB,
    error TEXT,
    cache_hit BOOLEAN DEFAULT FALSE,
    outcome VARCHAR(32),
    progress JSONB DEFAULT '{}',
    elapsed_ms FLOAT,
    cost_usd FLOAT,
    usage JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id ON workflow_runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_updated_at ON workflow_runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_queue_claim
    ON workflow_runs(queue_name, status, available_at, priority DESC, created_at)
    WHERE cancel_requested = FALSE;
CREATE INDEX IF NOT EXISTS idx_workflow_runs_stale_lease
    ON workflow_runs(queue_name, heartbeat_at)
    WHERE status = 'running' AND cancel_requested = FALSE;
CREATE INDEX IF NOT EXISTS idx_node_logs_run_id ON node_execution_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_node_logs_status ON node_execution_logs(status);
CREATE INDEX IF NOT EXISTS idx_node_logs_pgvector_index_id
    ON node_execution_logs ((output->>'index_id'))
    WHERE module_type = 'pgvector_index_writer';
"""

__all__ = ["WORKFLOW_SCHEMA_SQL"]
