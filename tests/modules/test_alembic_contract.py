from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_one_linear_schema_baseline() -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(root / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    heads = scripts.get_heads()
    baseline = scripts.get_revision("20260827_0001")

    assert heads == ["20260827_0001"]
    assert baseline is not None
    assert baseline.down_revision is None


def test_ci_applies_migrations_before_backend_tests() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    migration = workflow.index("uv run alembic upgrade head")
    tests = workflow.index("uv run pytest")
    assert migration < tests
