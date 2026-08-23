"""Executable dependency rules for the cleaned application architecture."""

from __future__ import annotations

import ast
from pathlib import Path
from textwrap import dedent

from jobs import ALL_JOBS, WorkerJobDefinition
from jobs.kubernetes import kubernetes_worker_specs

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _python_files(relative_root: str) -> list[Path]:
    return sorted((PROJECT_ROOT / relative_root).rglob("*.py"))


def test_features_never_import_http_api_layer() -> None:
    violations: list[str] = []
    for path in _python_files("backend/features"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "backend.api"
            ):
                violations.append(str(path.relative_to(PROJECT_ROOT)))
            if isinstance(node, ast.Import):
                if any(alias.name.startswith("backend.api") for alias in node.names):
                    violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert not violations, f"feature -> API layer inversion: {sorted(set(violations))}"


def test_modules_do_not_construct_infrastructure_clients() -> None:
    forbidden = {
        "DatabaseManager",
        "EmbeddingArtifactStore",
        "OpenAIProvider",
        "OpenAIResponsesClient",
        "PgVectorStore",
        "WorkbookCatalog",
    }
    violations: list[str] = []
    for path in _python_files("modules"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = function.id if isinstance(function, ast.Name) else None
            if name in forbidden:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
    assert not violations, f"module infrastructure construction: {violations}"


def test_kubernetes_specs_are_projected_from_worker_jobs() -> None:
    specs = kubernetes_worker_specs(ALL_JOBS)
    by_name = {spec.deployment_name: spec for spec in specs}
    assert len(by_name) == 4
    assert "workflow-worker" in by_name
    for job in ALL_JOBS:
        if not isinstance(job, WorkerJobDefinition):
            continue
        spec = by_name[job.kubernetes.deployment_name]
        assert spec.queue_name == job.queue_name
        assert spec.worker_module == job.worker_module
        assert spec.pending_query == dedent(job.kubernetes.pending_query).strip()


def test_feature_packages_do_not_own_kubernetes_yaml() -> None:
    assert not list((PROJECT_ROOT / "backend" / "features").glob("**/kubernetes/*.yaml"))


def test_kubernetes_tooling_uses_the_locked_project_python() -> None:
    script = (PROJECT_ROOT / "deploy" / "kubernetes" / "local.sh").read_text(
        encoding="utf-8"
    )
    assert 'PROJECT_PYTHON="${PROJECT_ROOT}/.venv/bin/python"' in script
    assert "python3" not in script
