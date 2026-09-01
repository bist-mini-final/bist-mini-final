"""Audit benchmark lifecycle changes without retaining questions or answers.

Revision ID: 20260901_0009
Revises: 20260901_0008
Create Date: 2026-09-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260901_0009"
down_revision: str | None = "20260901_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record safe benchmark state transitions in the append-only audit log."""

    op.execute(
        """
        CREATE OR REPLACE FUNCTION capture_benchmark_job_audit_log()
        RETURNS TRIGGER AS $$
        DECLARE
            before_payload JSONB;
            after_payload JSONB;
            resolved_job_id TEXT;
        BEGIN
            before_payload := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN
                jsonb_build_object(
                    'status', OLD.status,
                    'completed', OLD.completed,
                    'total', OLD.total,
                    'pause_requested', OLD.pause_requested,
                    'cancel_requested', OLD.cancel_requested,
                    'attempt_count', OLD.attempt_count,
                    'has_error', OLD.error IS NOT NULL
                )
            END;
            after_payload := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN
                jsonb_build_object(
                    'status', NEW.status,
                    'completed', NEW.completed,
                    'total', NEW.total,
                    'pause_requested', NEW.pause_requested,
                    'cancel_requested', NEW.cancel_requested,
                    'attempt_count', NEW.attempt_count,
                    'has_error', NEW.error IS NOT NULL
                )
            END;
            resolved_job_id := COALESCE(NEW.job_id, OLD.job_id);

            INSERT INTO audit_logs (
                entity_type,
                entity_id,
                action,
                actor_id,
                request_id,
                before_state,
                after_state
            ) VALUES (
                'benchmark_jobs',
                resolved_job_id,
                LOWER(TG_OP),
                NULLIF(current_setting('app.audit_actor_id', TRUE), ''),
                NULLIF(current_setting('app.audit_request_id', TRUE), ''),
                before_payload,
                after_payload
            );
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_benchmark_jobs_audit_insert ON benchmark_jobs;
        CREATE TRIGGER trg_benchmark_jobs_audit_insert
        AFTER INSERT ON benchmark_jobs
        FOR EACH ROW EXECUTE FUNCTION capture_benchmark_job_audit_log();

        DROP TRIGGER IF EXISTS trg_benchmark_jobs_audit_update ON benchmark_jobs;
        CREATE TRIGGER trg_benchmark_jobs_audit_update
        AFTER UPDATE OF status, pause_requested, cancel_requested ON benchmark_jobs
        FOR EACH ROW
        WHEN (
            OLD.status IS DISTINCT FROM NEW.status
            OR OLD.pause_requested IS DISTINCT FROM NEW.pause_requested
            OR OLD.cancel_requested IS DISTINCT FROM NEW.cancel_requested
        )
        EXECUTE FUNCTION capture_benchmark_job_audit_log();

        DROP TRIGGER IF EXISTS trg_benchmark_jobs_audit_delete ON benchmark_jobs;
        CREATE TRIGGER trg_benchmark_jobs_audit_delete
        AFTER DELETE ON benchmark_jobs
        FOR EACH ROW EXECUTE FUNCTION capture_benchmark_job_audit_log();
        """
    )


def downgrade() -> None:
    """Preserve existing audit history while removing benchmark producers."""

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_benchmark_jobs_audit_insert ON benchmark_jobs;
        DROP TRIGGER IF EXISTS trg_benchmark_jobs_audit_update ON benchmark_jobs;
        DROP TRIGGER IF EXISTS trg_benchmark_jobs_audit_delete ON benchmark_jobs;
        DROP FUNCTION IF EXISTS capture_benchmark_job_audit_log();
        """
    )
