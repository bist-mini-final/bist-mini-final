from backend.features.bi.database_schema import BI_SCHEMA_SQL
from backend.storage.audit_schema import AUDIT_SCHEMA_SQL
from backend.storage.db_manager import DDL_INIT


def test_source_files_and_bi_companies_have_soft_delete_contract() -> None:
    assert "is_deleted BOOLEAN NOT NULL DEFAULT FALSE" in DDL_INIT
    assert "deleted_at TIMESTAMPTZ" in DDL_INIT
    assert "idx_source_files_active" in DDL_INIT
    assert "is_deleted BOOLEAN NOT NULL DEFAULT FALSE" in BI_SCHEMA_SQL
    assert "deleted_at TIMESTAMPTZ" in BI_SCHEMA_SQL
    assert "idx_bi_companies_active" in BI_SCHEMA_SQL


def test_audit_log_is_triggered_and_append_only() -> None:
    assert "CREATE TABLE IF NOT EXISTS audit_logs" in AUDIT_SCHEMA_SQL
    assert "capture_entity_audit_log" in DDL_INIT
    assert "trg_source_files_audit" in DDL_INIT
    assert "trg_bi_companies_audit" in BI_SCHEMA_SQL
    assert "trg_audit_logs_immutable" in AUDIT_SCHEMA_SQL
    assert "audit_logs is append-only" in AUDIT_SCHEMA_SQL
