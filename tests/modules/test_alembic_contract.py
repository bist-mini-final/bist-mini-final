from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_linear_baseline_and_soft_delete_revision() -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(root / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    heads = scripts.get_heads()
    baseline = scripts.get_revision("20260827_0001")

    soft_delete = scripts.get_revision("20260828_0002")

    assert heads == ["20260828_0002"]
    assert baseline is not None
    assert baseline.down_revision is None
    assert soft_delete is not None
    assert soft_delete.down_revision == "20260827_0001"


def test_ci_applies_migrations_before_backend_tests() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    migration = workflow.index("uv run alembic upgrade head")
    tests = workflow.index("uv run pytest")
    assert migration < tests
