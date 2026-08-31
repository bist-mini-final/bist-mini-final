"""Prevent new cyclomatic-complexity debt while legacy hotspots are retired."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPLEXITY_PATTERN = re.compile(r"^`([^`]+)` is too complex \((\d+) > 10\)$")

# Every previous hotspot has been retired. Keep the explicit map so any future
# exception must be reviewed as visible migration debt instead of being hidden
# behind a blanket C901 exemption.
LEGACY_COMPLEXITY_BUDGETS: dict[tuple[str, str], int] = {}


def _complexity_violations() -> dict[tuple[str, str], int]:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "backend",
            "modules",
            "--select",
            "C901",
            "--config",
            "lint.mccabe.max-complexity=10",
            "--output-format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode in {0, 1}, process.stderr
    violations: dict[tuple[str, str], int] = {}
    for item in json.loads(process.stdout):
        match = COMPLEXITY_PATTERN.match(item["message"])
        assert match is not None, item
        relative_path = Path(item["filename"]).resolve().relative_to(PROJECT_ROOT).as_posix()
        violations[(relative_path, match.group(1))] = int(match.group(2))
    return violations


def test_backend_complexity_does_not_exceed_the_migration_budget() -> None:
    observed = _complexity_violations()
    unexpected = set(observed) - set(LEGACY_COMPLEXITY_BUDGETS)
    exceeded = {
        key: (value, LEGACY_COMPLEXITY_BUDGETS[key])
        for key, value in observed.items()
        if key in LEGACY_COMPLEXITY_BUDGETS and value > LEGACY_COMPLEXITY_BUDGETS[key]
    }
    assert not unexpected, f"new C901 hotspots: {sorted(unexpected)}"
    assert not exceeded, f"increased C901 complexity: {exceeded}"
