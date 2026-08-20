"""Validation tests for local Kubernetes deployment helpers."""

from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "arguments",
    [
        ["--cpu-per-job", "0"],
        ["--memory-per-job-gib", "-1"],
        ["--hard-cap", "0"],
        ["--reserve-cpu", "-0.1"],
        ["--reserve-memory-gib", "-1"],
    ],
)
def test_capacity_cli_rejects_invalid_resource_values(arguments: list[str]) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "deploy/kubernetes/capacity.py"),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "error:" in result.stderr


@pytest.mark.parametrize(
    ("endpoint", "address_type"),
    [("172.20.0.2", "IPv4"), ("2001:db8::2", "IPv6")],
)
def test_database_endpoint_renderer_uses_ip_version(
    endpoint: str,
    address_type: str,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "deploy/kubernetes/render_database.py"),
            "--endpoint",
            endpoint,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert f"addressType: {address_type}" in result.stdout
    assert f"- {endpoint}" in result.stdout
    assert "__ADDRESS_TYPE__" not in result.stdout
