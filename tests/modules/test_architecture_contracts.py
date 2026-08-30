"""Executable dependency rules for the cleaned application architecture."""

from __future__ import annotations

import ast
from pathlib import Path
from textwrap import dedent
from typing import get_type_hints

from backend.bootstrap.container import (
    ApplicationContainer,
    DomainServicesContainer,
    ExecutionContainer,
)
from backend.engine.worker.base import LeasedWorker
from backend.features.bi.materialization_worker_main import BiMaterializationWorker
from backend.features.chatbot.repository import ChatSessionRepository
from backend.shared.infrastructure.database import SyncPostgresRepository
from backend.storage.data_sources.embedding_shard_worker_main import (
    EmbeddingShardWorker,
)
from backend.storage.data_sources.vector_shard_worker_main import VectorShardWorker
from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.repositories import (
    PgVectorRetrievalMixin,
    SourceFileRepositoryMixin,
    WorkflowRunRepositoryMixin,
)
from jobs import ALL_JOBS, WorkerJobDefinition
from jobs.kubernetes import kubernetes_worker_specs

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_application_container_is_split_by_runtime_responsibility() -> None:
    annotations = get_type_hints(ApplicationContainer)
    assert annotations["execution"] is ExecutionContainer
    assert annotations["domain"] is DomainServicesContainer


def _python_files(relative_root: str) -> list[Path]:
    return sorted((PROJECT_ROOT / relative_root).rglob("*.py"))


def test_features_never_import_http_api_layer() -> None:
    violations: list[str] = []
    for path in _python_files("backend/features"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("backend.api"):
                violations.append(str(path.relative_to(PROJECT_ROOT)))
            if isinstance(node, ast.Import):
                if any(alias.name.startswith("backend.api") for alias in node.names):
                    violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert not violations, f"feature -> API layer inversion: {sorted(set(violations))}"


def test_domain_packages_do_not_import_outer_layers() -> None:
    forbidden_prefixes = (
        "backend.api",
        "backend.platform",
        "backend.providers",
        "backend.storage",
    )
    violations: list[str] = []
    for path in _python_files("backend/domains"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            elif isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            if any(name.startswith(forbidden_prefixes) for name in imported):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{getattr(node, 'lineno', 0)}")
    assert not violations, f"domain -> outer layer dependency: {violations}"


def test_framework_state_access_is_confined_to_the_composition_boundary() -> None:
    allowed = {
        Path("backend/api/dependencies.py"),
        Path("backend/main.py"),
    }
    violations: list[str] = []
    for path in _python_files("backend"):
        relative = path.relative_to(PROJECT_ROOT)
        if relative in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        if ".app.state" in source or "application.state" in source:
            violations.append(str(relative))
    assert not violations, f"framework state escaped composition boundary: {violations}"


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


def test_pipeline_modules_depend_on_pgvector_ports_not_the_sql_gateway() -> None:
    violations: list[str] = []
    for path in _python_files("modules"):
        source = path.read_text(encoding="utf-8")
        if "backend.storage.pgvector_store" in source:
            violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert not violations, f"module -> pgvector SQL gateway dependency: {violations}"


def test_feature_repositories_do_not_reach_into_private_database_connections() -> None:
    violations: list[str] = []
    for path in _python_files("backend/features"):
        source = path.read_text(encoding="utf-8")
        if "._raw_connection(" in source:
            violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert not violations, f"private database connection access: {violations}"


def test_chat_repository_uses_shared_postgres_repository_boundary() -> None:
    assert issubclass(ChatSessionRepository, SyncPostgresRepository)


def test_database_facades_compose_focused_storage_capabilities() -> None:
    assert issubclass(DatabaseManager, SourceFileRepositoryMixin)
    assert issubclass(DatabaseManager, WorkflowRunRepositoryMixin)
    assert issubclass(PgVectorStore, PgVectorRetrievalMixin)


def test_one_shot_workers_share_the_leased_worker_template() -> None:
    assert issubclass(EmbeddingShardWorker, LeasedWorker)
    assert issubclass(VectorShardWorker, LeasedWorker)
    assert issubclass(BiMaterializationWorker, LeasedWorker)


def test_kubernetes_specs_are_projected_from_worker_jobs() -> None:
    specs = kubernetes_worker_specs(ALL_JOBS)
    by_name = {spec.deployment_name: spec for spec in specs}
    assert len(by_name) == 6
    assert "workflow-worker" in by_name
    assert by_name["ingestion-embedding"].max_replica_count == 4
    assert by_name["ingestion-vector"].max_replica_count == 2
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
    script = (PROJECT_ROOT / "deploy" / "kubernetes" / "local.sh").read_text(encoding="utf-8")
    assert 'PROJECT_PYTHON="${PROJECT_ROOT}/.venv/bin/python"' in script
    assert "python3" not in script


def test_execution_views_share_the_streaming_core() -> None:
    frontend = PROJECT_ROOT / "frontend" / "src"
    playground_api = (frontend / "features" / "playground" / "services" / "api.ts").read_text(
        encoding="utf-8"
    )
    ingestion_api = (
        frontend / "features" / "data-sources" / "services" / "dataSourceApi.ts"
    ).read_text(encoding="utf-8")
    ingestion_view = (frontend / "features" / "data-sources" / "DataSourcesView.tsx").read_text(
        encoding="utf-8"
    )

    assert "observeWorkflowRun" in playground_api
    assert "observeWorkflowRun" in ingestion_api
    assert "setInterval" not in ingestion_view


def test_bi_product_route_never_uses_dashboard_fixtures() -> None:
    frontend = PROJECT_ROOT / "frontend" / "src"
    route = (frontend / "pages" / "BiPage.tsx").read_text(encoding="utf-8")
    production_bi_files = [
        path
        for path in (frontend / "features" / "bi").rglob("*.ts*")
        if "__tests__" not in path.parts
    ]

    assert "features/bi/BiPage" in route
    assert not (frontend / "features" / "bi" / "BiView.tsx").exists()
    assert all(
        "dashboardFixtures" not in path.read_text(encoding="utf-8") for path in production_bi_files
    )
