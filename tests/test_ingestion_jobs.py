from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.data_sources import (
    INGESTION_WORKFLOW_IDS,
    IngestionJobService,
    IngestionRequest,
)
from backend.data_sources.ingestion_registry import IngestionModuleRegistry
from backend.core.settings import WORKFLOW_DIR
from backend.storage.answer_cache import AnswerCacheRepository
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.vector_index import VectorIndexStore
from backend.workflows import WorkflowStore


def _service():
    workflow = SimpleNamespace(
        graph=SimpleNamespace(
            nodes=[
                SimpleNamespace(id="selector", module_type="processed_file_selector"),
                SimpleNamespace(id="serializer", module_type="cell_text_serializer"),
                SimpleNamespace(id="embedder", module_type="cell_text_embedder"),
                SimpleNamespace(id="writer", module_type="pgvector_index_writer"),
            ]
        )
    )
    workflow_store = MagicMock()
    workflow_store.load.return_value = workflow
    run_store = MagicMock()
    executor = MagicMock()
    run = SimpleNamespace(id="run-ingestion")
    executor.create_run.return_value = run
    run_store.load_summary.return_value = run
    dispatcher = MagicMock()
    service = IngestionJobService(
        workflow_store,
        run_store,
        executor,
        dispatcher,
    )
    return service, workflow_store, executor, dispatcher, run


def test_create_and_submit_builds_persisted_excel_ingestion_request() -> None:
    service, workflow_store, executor, dispatcher, run = _service()

    result = service.create_and_submit(
        IngestionRequest(
            file_name="sample.xlsx",
            sheet_names=["Summary"],
            model="text-embedding-3-small",
            variant_mode="header_with_value",
            batch_size=128,
        )
    )

    assert result is run
    workflow_store.load.assert_called_once_with("indexing_pgvector")
    _, request = executor.create_run.call_args.args
    assert request.inputs == {
        "selector": {
            "file_name": "sample.xlsx",
            "sheet_names": ["Summary"],
        }
    }
    assert request.config_overrides == {
        "serializer": {"variant_mode": "header_with_value"},
        "embedder": {
            "model": "text-embedding-3-small",
            "batch_size": 128,
        },
    }
    dispatcher.submit.assert_called_once_with("run-ingestion")
    service.run_store.load_summary.assert_called_once_with("run-ingestion")


def test_exhaustive_mode_selects_exhaustive_workflow() -> None:
    service, workflow_store, _, _, _ = _service()

    service.create_run(
        IngestionRequest(file_name="sample.xlsx", structure_mode="exhaustive")
    )

    workflow_store.load.assert_called_once_with("indexing_pgvector_exhaustive")


def test_load_rejects_non_ingestion_run() -> None:
    service, _, _, _, _ = _service()
    service.run_store.load.return_value = SimpleNamespace(
        id="run-rag",
        workflow_id="main_pgvector_rag_pipeline",
    )

    with pytest.raises(FileNotFoundError):
        service.load("run-rag")


def test_recover_pending_is_scoped_to_ingestion_workflows() -> None:
    service, _, _, dispatcher, _ = _service()
    dispatcher.recover_pending.return_value = 2

    assert service.recover_pending() == 2
    dispatcher.recover_pending.assert_called_once_with(INGESTION_WORKFLOW_IDS)


def test_ingestion_registry_loads_only_ingestion_modules_without_child_worker() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        registry = IngestionModuleRegistry(
            AnswerCacheRepository(root / "answers.json"),
            embedding_artifact_store=EmbeddingArtifactStore(root / "embeddings"),
            vector_index_store=VectorIndexStore(root / "indexes"),
            pgvector_store=MagicMock(),
            db_manager=MagicMock(),
            processed_dir=root / "source_files",
            spreadsheet_artifact_dir=root / "spreadsheets",
        )

        assert {item["type"] for item in registry.definitions()} == {
            "processed_file_selector",
            "luna_vlm_structure_detector",
            "cell_text_serializer",
            "exhaustive_cell_text_serializer",
            "cell_text_embedder",
            "pgvector_index_writer",
            "company_entity_extractor",
            "sheet_metadata_persistence",
            "index_company_persistence",
        }
        assert registry.isolated_worker_spec is None
        registered = {item["type"] for item in registry.definitions()}
        workflow_store = WorkflowStore(WORKFLOW_DIR)
        for workflow_id in INGESTION_WORKFLOW_IDS:
            workflow = workflow_store.load(workflow_id)
            assert {node.module_type for node in workflow.graph.nodes} <= registered
