from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_linear_snapshot_revision_chain() -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(root / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    heads = scripts.get_heads()
    baseline = scripts.get_revision("20260827_0001")

    soft_delete = scripts.get_revision("20260828_0002")
    domain_snapshots = scripts.get_revision("20260828_0003")
    scoped_snapshot_heads = scripts.get_revision("20260828_0004")
    ingestion_shards = scripts.get_revision("20260829_0005")
    workbook_profiles = scripts.get_revision("20260831_0006")
    chat_message_evidence = scripts.get_revision("20260831_0007")
    chat_message_completion_time = scripts.get_revision("20260901_0008")

    assert heads == ["20260901_0008"]
    assert baseline is not None
    assert baseline.down_revision is None
    assert soft_delete is not None
    assert soft_delete.down_revision == "20260827_0001"
    assert domain_snapshots is not None
    assert domain_snapshots.down_revision == "20260828_0002"
    assert scoped_snapshot_heads is not None
    assert scoped_snapshot_heads.down_revision == "20260828_0003"
    assert ingestion_shards is not None
    assert ingestion_shards.down_revision == "20260828_0004"
    assert workbook_profiles is not None
    assert workbook_profiles.down_revision == "20260829_0005"
    assert chat_message_evidence is not None
    assert chat_message_evidence.down_revision == "20260831_0006"
    assert chat_message_completion_time is not None
    assert chat_message_completion_time.down_revision == "20260831_0007"


def test_ci_applies_migrations_before_backend_tests() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    migration = workflow.index("uv run alembic upgrade head")
    tests = workflow.index("uv run pytest")
    assert migration < tests
