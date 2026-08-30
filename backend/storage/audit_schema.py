from typing import Final

AUDIT_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    action VARCHAR(16) NOT NULL CHECK (action IN ('insert', 'update', 'delete')),
    actor_id VARCHAR(128),
    request_id VARCHAR(128),
    before_state JSONB,
    after_state JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (before_state IS NOT NULL OR after_state IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity
    ON audit_logs(entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_request
    ON audit_logs(request_id, occurred_at DESC)
    WHERE request_id IS NOT NULL;

CREATE OR REPLACE FUNCTION capture_entity_audit_log()
RETURNS TRIGGER AS $$
DECLARE
    before_payload JSONB;
    after_payload JSONB;
    resolved_entity_id TEXT;
BEGIN
    before_payload := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    after_payload := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
    resolved_entity_id := COALESCE(
        after_payload->>'file_id',
        after_payload->>'company_id',
        before_payload->>'file_id',
        before_payload->>'company_id'
    );
    INSERT INTO audit_logs (
        entity_type,
        entity_id,
        action,
        actor_id,
        request_id,
        before_state,
        after_state
    ) VALUES (
        TG_TABLE_NAME,
        resolved_entity_id,
        LOWER(TG_OP),
        NULLIF(current_setting('app.audit_actor_id', TRUE), ''),
        NULLIF(current_setting('app.audit_request_id', TRUE), ''),
        before_payload,
        after_payload
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;
CREATE TRIGGER trg_audit_logs_immutable
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
"""

SOURCE_FILE_AUDIT_SQL: Final = """
DROP TRIGGER IF EXISTS trg_source_files_audit ON source_files;
CREATE TRIGGER trg_source_files_audit
AFTER INSERT OR UPDATE OR DELETE ON source_files
FOR EACH ROW EXECUTE FUNCTION capture_entity_audit_log();
"""

BI_COMPANY_AUDIT_SQL: Final = """
DROP TRIGGER IF EXISTS trg_bi_companies_audit ON bi_companies;
CREATE TRIGGER trg_bi_companies_audit
AFTER INSERT OR UPDATE OR DELETE ON bi_companies
FOR EACH ROW EXECUTE FUNCTION capture_entity_audit_log();
"""

__all__ = ["AUDIT_SCHEMA_SQL", "BI_COMPANY_AUDIT_SQL", "SOURCE_FILE_AUDIT_SQL"]
