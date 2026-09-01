"""Executable dependency rules for the cleaned application architecture."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from textwrap import dedent
from typing import get_type_hints

from backend.bootstrap.application import (
    ApplicationContainer,
    DomainServicesContainer,
    ExecutionContainer,
)
from backend.domains.bi.workers.materialization import BiMaterializationWorker
from backend.domains.chatbot.infrastructure.postgres import ChatSessionRepository
from backend.domains.data_sources.infrastructure.pgvector import (
    PgVectorCatalogMixin,
    PgVectorRetrievalMixin,
    PgVectorStore,
    PgVectorWriteMixin,
)
from backend.domains.data_sources.infrastructure.postgres import PostgresSourceFileRepository
from backend.domains.data_sources.workers.embedding import (
    EmbeddingShardWorker,
)
from backend.domains.data_sources.workers.vector import VectorShardWorker
from backend.domains.workflow.infrastructure.postgres import (
    PostgresWorkflowRunRepository,
    WorkflowRunHistoryRepositoryMixin,
    WorkflowRunQueueRepositoryMixin,
    WorkflowRunStateRepositoryMixin,
)
from backend.platform.postgres.repositories import SyncPostgresRepository
from backend.shared.application.workers import LeasedWorker
from jobs import ALL_JOBS, WorkerJobDefinition
from jobs.kubernetes import kubernetes_worker_specs

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_application_container_is_split_by_runtime_responsibility() -> None:
    annotations = get_type_hints(ApplicationContainer)
    assert annotations["execution"] is ExecutionContainer
    assert annotations["domain"] is DomainServicesContainer


def _python_files(relative_root: str) -> list[Path]:
    return sorted((PROJECT_ROOT / relative_root).rglob("*.py"))


def _imported_modules(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append((node.module or "", node.lineno))
        elif isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
    return imports


def test_application_code_uses_canonical_stage_one_boundaries() -> None:
    legacy_prefixes = (
        "backend.bootstrap.container",
        "backend.core.state_stream",
        "backend.core.state_stream_broker",
        "backend.core.telemetry",
        "backend.engine.job_catalog",
        "backend.engine.orchestration",
        "backend.engine.runtime",
        "backend.engine.workflows",
        "backend.engine.worker.base",
        "backend.engine.worker.lease",
        "backend.providers.embeddings",
        "backend.providers.openai_pricing",
        "backend.providers.openai_provider",
        "backend.providers.openai_responses",
        "backend.shared.infrastructure.database",
        "backend.shared.infrastructure.observability",
        "backend.storage.connection_pool",
        "backend.storage.data_sources",
        "backend.storage.embedding_artifacts",
        "backend.storage.spreadsheets",
        "backend.platform.data_sources",
        "backend.api.data_source_controller",
        "backend.api.data_source_database_routes",
        "backend.api.data_source_file_routes",
        "backend.api.data_source_index_routes",
        "backend.api.data_source_ingestion_controller",
        "backend.api.data_source_ingestion_routes",
        "backend.api.data_source_routes",
        "backend.features.bi",
        "backend.api.bi_routes",
        "backend.storage.audit_schema",
        "backend.api.company_comparison_routes",
        "backend.api.chat_routes",
        "backend.features.chatbot",
        "backend.api.benchmark_routes",
        "backend.features.benchmark",
        "backend.api.job_routes",
        "backend.features.job_monitoring",
        "backend.providers.kubernetes_monitor",
        "backend.api.cell_evidence_routes",
        "backend.api.module_routes",
        "backend.api.spreadsheet_artifact_routes",
        "backend.domains.company_comparison.errors",
        "backend.domains.company_comparison.league_scoring",
        "backend.domains.company_comparison.models",
        "backend.domains.company_comparison.snapshot_builder",
        "backend.contracts.snapshots",
        "backend.storage.versioned_snapshot_store",
        "backend.storage.db_manager",
        "backend.storage.repositories",
        "backend.api.workflow_controller",
        "backend.api.workflow_routes",
    )
    violations: list[str] = []
    for root in ("backend", "modules", "jobs"):
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(legacy_prefixes):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}")
    assert not violations, f"legacy stage-one imports remain: {violations}"


def test_api_package_contains_only_common_http_composition() -> None:
    allowed = {
        "__init__.py",
        "error_mapping.py",
        "exception_handlers.py",
        "middleware.py",
        "openapi.py",
        "router.py",
        "spa.py",
        "system_routes.py",
        "versioning.py",
    }
    actual = {path.name for path in (PROJECT_ROOT / "backend/api").glob("*.py")}
    assert actual == allowed


def test_removed_horizontal_compatibility_packages_have_no_python_sources() -> None:
    removed = (
        "backend/contracts",
        "backend/cli",
        "backend/engine",
        "backend/features",
        "backend/providers",
        "backend/storage",
    )
    remaining = {
        root: [str(path.relative_to(PROJECT_ROOT)) for path in _python_files(root)]
        for root in removed
        if _python_files(root)
    }
    assert not remaining, f"removed compatibility sources remain: {remaining}"


def test_backend_root_contains_no_legacy_process_module() -> None:
    assert not (PROJECT_ROOT / "backend/main.py").exists()


def test_removed_repository_directories_do_not_reappear() -> None:
    removed = (
        "notebooks",
        "frontend/src/features/company-comparison-v2",
        "jobs/workflow_worker",
        "backend/entrypoints/commands/documentation",
        "backend/platform/data_sources",
        "backend/contracts",
        "backend/data_sources",
        "backend/documentation",
        "backend/embeddings",
        "backend/engine",
        "backend/features",
        "backend/llm",
        "backend/modules",
        "backend/orchestration",
        "backend/providers",
        "backend/retrieval",
        "backend/runtime",
        "backend/spreadsheets",
        "backend/storage",
        "backend/vision",
        "backend/workflows",
        "data/processed",
        "data/raw",
        "data/virtual",
    )
    remaining = [path for path in removed if (PROJECT_ROOT / path).exists()]
    assert not remaining, f"removed repository directories remain: {remaining}"


def test_backend_python_sources_use_the_target_top_level_packages() -> None:
    allowed = {
        "api",
        "bootstrap",
        "core",
        "domains",
        "entrypoints",
        "platform",
        "shared",
    }
    actual = {
        path.relative_to(PROJECT_ROOT / "backend").parts[0]
        for path in _python_files("backend")
        if len(path.relative_to(PROJECT_ROOT / "backend").parts) > 1
    }
    assert actual == allowed
    core_files = {
        path.name for path in _python_files("backend/core")
    }
    assert core_files == {"__init__.py", "settings.py"}


def test_workflow_vertical_slice_has_no_legacy_or_inverted_dependencies() -> None:
    forbidden_by_layer = {
        "domain": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "application": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "presentation": (
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.workflow.infrastructure",
        ),
        "workers": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.workflow.infrastructure",
        ),
    }
    violations: list[str] = []
    for layer, forbidden in forbidden_by_layer.items():
        root = f"backend/domains/workflow/{layer}"
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(forbidden):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}")
    assert not violations, f"workflow layer inversion: {violations}"


def test_data_sources_vertical_slice_has_no_legacy_or_inverted_dependencies() -> None:
    forbidden_by_layer = {
        "domain": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "application": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "presentation": (
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.data_sources.infrastructure",
        ),
        "workers": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.data_sources.infrastructure",
        ),
    }
    violations: list[str] = []
    for layer, forbidden in forbidden_by_layer.items():
        root = f"backend/domains/data_sources/{layer}"
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}"
                    )
    assert not violations, f"data sources layer inversion: {violations}"


def test_bi_vertical_slice_has_no_legacy_or_inverted_dependencies() -> None:
    forbidden_by_layer = {
        "domain": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "application": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "presentation": (
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.bi.infrastructure",
        ),
        "workers": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.bi.infrastructure",
        ),
    }
    violations: list[str] = []
    for layer, forbidden in forbidden_by_layer.items():
        root = f"backend/domains/bi/{layer}"
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}"
                    )
    assert not violations, f"BI layer inversion: {violations}"


def test_company_comparison_vertical_slice_has_no_inverted_dependencies() -> None:
    forbidden_by_layer = {
        "domain": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "application": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.company_comparison.infrastructure",
        ),
        "presentation": (
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.company_comparison.infrastructure",
        ),
    }
    violations: list[str] = []
    for layer, forbidden in forbidden_by_layer.items():
        root = f"backend/domains/company_comparison/{layer}"
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}"
                    )
    assert not violations, f"company comparison layer inversion: {violations}"


def test_chatbot_vertical_slice_has_no_inverted_dependencies() -> None:
    forbidden_by_layer = {
        "domain": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "application": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.chatbot.infrastructure",
        ),
        "presentation": (
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.chatbot.infrastructure",
        ),
    }
    violations: list[str] = []
    for layer, forbidden in forbidden_by_layer.items():
        root = f"backend/domains/chatbot/{layer}"
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}"
                    )
    assert not violations, f"chatbot layer inversion: {violations}"


def test_benchmark_vertical_slice_has_no_inverted_dependencies() -> None:
    forbidden_by_layer = {
        "domain": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "application": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.benchmark.infrastructure",
        ),
        "presentation": (
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.benchmark.infrastructure",
        ),
        "workers": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.benchmark.infrastructure",
        ),
    }
    violations: list[str] = []
    for layer, forbidden in forbidden_by_layer.items():
        root = f"backend/domains/benchmark/{layer}"
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}"
                    )
    assert not violations, f"benchmark layer inversion: {violations}"


def test_operations_vertical_slice_has_no_inverted_dependencies() -> None:
    forbidden_by_layer = {
        "domain": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
        ),
        "application": (
            "backend.api",
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.operations.infrastructure",
        ),
        "presentation": (
            "backend.bootstrap",
            "backend.engine",
            "backend.features",
            "backend.platform",
            "backend.providers",
            "backend.storage",
            "backend.domains.operations.infrastructure",
        ),
    }
    violations: list[str] = []
    for layer, forbidden in forbidden_by_layer.items():
        root = f"backend/domains/operations/{layer}"
        for path in _python_files(root):
            for imported, line in _imported_modules(path):
                if imported.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}"
                    )
    assert not violations, f"operations layer inversion: {violations}"


def test_process_entrypoints_only_import_bootstrap() -> None:
    violations: list[str] = []
    for path in _python_files("backend/entrypoints"):
        for imported, line in _imported_modules(path):
            if imported.startswith("backend.") and not imported.startswith(
                "backend.bootstrap"
            ):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line} -> {imported}")
    assert not violations, f"entrypoint bypassed bootstrap: {violations}"


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


def test_domain_core_and_application_do_not_import_outer_layers() -> None:
    always_forbidden = ("backend.api", "backend.providers", "backend.storage")
    violations: list[str] = []
    for path in _python_files("backend/domains"):
        relative = path.relative_to(PROJECT_ROOT)
        is_domain_infrastructure = "infrastructure" in relative.parts
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            elif isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            forbidden_prefixes = (
                always_forbidden
                if is_domain_infrastructure
                else (*always_forbidden, "backend.platform")
            )
            if any(name.startswith(forbidden_prefixes) for name in imported):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{getattr(node, 'lineno', 0)}")
    assert not violations, f"domain -> outer layer dependency: {violations}"


def test_framework_state_access_is_confined_to_the_composition_boundary() -> None:
    allowed: set[Path] = set()
    violations: list[str] = []
    for path in _python_files("backend"):
        relative = path.relative_to(PROJECT_ROOT)
        if relative in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        if re.search(r"\b(?:app|application)\.state\b", source):
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
        if "infrastructure.pgvector.store" in source:
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


def test_domain_repositories_compose_focused_postgres_capabilities() -> None:
    assert issubclass(PostgresSourceFileRepository, SyncPostgresRepository)
    assert issubclass(PostgresWorkflowRunRepository, WorkflowRunQueueRepositoryMixin)
    assert issubclass(PostgresWorkflowRunRepository, WorkflowRunStateRepositoryMixin)
    assert issubclass(PostgresWorkflowRunRepository, WorkflowRunHistoryRepositoryMixin)
    assert issubclass(PgVectorStore, PgVectorWriteMixin)
    assert issubclass(PgVectorStore, PgVectorCatalogMixin)
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
    assert by_name["bi-materialization"].mount_data_volume is True
    assert by_name["bi-question"].mount_data_volume is True
    for job in ALL_JOBS:
        if not isinstance(job, WorkerJobDefinition):
            continue
        spec = by_name[job.kubernetes.deployment_name]
        assert spec.queue_name == job.queue_name
        assert spec.worker_module == job.worker_module
        assert spec.arguments == (job.worker_kind,)
        assert spec.pending_query == dedent(job.kubernetes.pending_query).strip()


def test_kubernetes_specs_use_the_unified_worker_entrypoint() -> None:
    specs = kubernetes_worker_specs(ALL_JOBS)
    assert {spec.worker_module for spec in specs} == {"backend.entrypoints.worker"}
    assert {spec.arguments[0] for spec in specs} == {
        "workflow",
        "ingestion-embedding",
        "ingestion-vector",
        "bi-materialization",
        "bi-question",
        "benchmark",
    }


def test_feature_packages_do_not_own_kubernetes_yaml() -> None:
    assert not list((PROJECT_ROOT / "backend" / "features").glob("**/kubernetes/*.yaml"))


def test_kubernetes_tooling_uses_the_locked_project_python() -> None:
    script = (PROJECT_ROOT / "deploy" / "kubernetes" / "local.sh").read_text(encoding="utf-8")
    assert 'PROJECT_PYTHON="${PROJECT_ROOT}/.venv/bin/python"' in script
    assert "python3" not in script


def test_kubernetes_worker_releases_do_not_mix_mutable_image_revisions() -> None:
    manifest = (
        PROJECT_ROOT / "deploy" / "kubernetes" / "manifests" / "scaledjob.yaml"
    ).read_text(encoding="utf-8")
    renderer = (
        PROJECT_ROOT / "deploy" / "kubernetes" / "scripts" / "render.py"
    ).read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deploy" / "kubernetes" / "local.sh").read_text(
        encoding="utf-8"
    )
    helm = (
        PROJECT_ROOT / "deploy" / "helm" / "bist" / "templates" / "scaledjobs.yaml"
    ).read_text(encoding="utf-8")
    assert "strategy: immediate" in manifest
    assert manifest.count("bist.ai/image-revision: __IMAGE_REVISION__") == 2
    assert 'parser.add_argument("--image-revision", required=True)' in renderer
    assert '--image-revision "${worker_revision}"' in script
    assert "strategy: immediate" in helm
    assert helm.count("bist.ai/image-revision:") == 2


def test_bi_workers_do_not_run_schema_ddl_during_keda_scale_out() -> None:
    workers = (PROJECT_ROOT / "backend" / "bootstrap" / "workers.py").read_text(
        encoding="utf-8"
    )
    assert "ensure_bi_schema" not in workers
    bi_branch = workers.split('if kind in {"bi-materialization", "bi-question"}:', 1)[1]
    bi_branch = bi_branch.split('if kind == "benchmark":', 1)[0]
    assert "initialize_schema=False" in bi_branch


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
