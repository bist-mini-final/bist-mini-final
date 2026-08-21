"""Unit and integration tests for v3 ultra-fast modular RAG components."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules.embedding.batch_query_embedder import (
    BatchQueryEmbedderExecutionDTO,
    BatchQueryEmbedderInputDTO,
    BatchQueryEmbedderModule,
)
from modules.common.base_module import DocumentContextDTO, QueryContextDTO
from modules.query.decomposer import SubqueriesDTO
from modules.retrieval.pg_context_expander import (
    PgContextExpanderExecutionDTO,
    PgContextExpanderInputDTO,
    PgContextExpanderModule,
    _parse_cell_id_coords,
)
from modules.retrieval.postgres_native_keyword_retriever import (
    PostgresNativeKeywordRetrieverExecutionDTO,
    PostgresNativeKeywordRetrieverInputDTO,
    PostgresNativeKeywordRetrieverModule,
    _clean_tsquery_term,
)
from modules.storage.pgvector_collection_loader import IndexOutputDTO
from modules.retrieval.retrieval_models import RetrievalDTO, RrfCandidateDTO
from backend.engine.runtime.registry import ModuleRegistry
from backend.storage.answer_cache import AnswerCacheRepository
from backend.storage.pgvector_store import PgVectorStore
from backend.engine.workflows.executor import WorkflowExecutor
from backend.engine.workflows.models import WorkflowDocument
from backend.engine.workflows.store import WorkflowStore


def test_clean_tsquery_term():
    assert _clean_tsquery_term("2024년! Total @Revenue?") == "2024년 Total Revenue"
    assert _clean_tsquery_term("") == ""


def test_parse_cell_id_coords():
    comp, sheet, r, c = _parse_cell_id_coords("IBM:Income_Statement:B15")
    assert comp == "IBM"
    assert sheet == "Income_Statement"
    assert r == 15
    assert c == 2

    comp2, sheet2, r2, c2 = _parse_cell_id_coords("Balance_Sheet:C20")
    assert comp2 == ""
    assert sheet2 == "Balance_Sheet"
    assert r2 == 20
    assert c2 == 3


def test_batch_query_embedder_mock():
    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    module = BatchQueryEmbedderModule(encoder=mock_encoder)
    qc = QueryContextDTO(
        question_id="Q1",
        question_text="Total Revenue",
    )
    payload = BatchQueryEmbedderExecutionDTO(
        query_input=SubqueriesDTO(
            query_context=qc,
            subqueries=["Total Revenue 2024", "Total Revenue 2023"],
        ),
        model="text-embedding-3-large",
    )
    res = module.execute(payload)
    assert "items" in res
    assert "Total Revenue 2024" in res["items"]
    assert "Total Revenue 2023" in res["items"]
    assert len(res["items"]["Total Revenue 2024"]) == 3
    mock_encoder.encode.assert_called_once_with(["Total Revenue 2024", "Total Revenue 2023"])


def test_pg_context_expander_formatting():
    mock_store = MagicMock(spec=PgVectorStore)
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_store._raw_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.return_value = [
        (
            "Total Revenue 2024: $62,000M",
            {
                "row_index": 15,
                "col_index": 2,
                "row_header": ["Revenue", "Total Revenue"],
                "column_header": ["2024"],
                "cell_value": "$62,000M",
            },
        )
    ]

    module = PgContextExpanderModule(pgvector_store=mock_store)
    qc = QueryContextDTO(question_id="Q1", question_text="Revenue?")
    dc = DocumentContextDTO(file_name="ibm.xlsx", workbook_hash="hash123")
    retrieval = RetrievalDTO(
        query_context=qc,
        document_context=dc,
        items=[
            RrfCandidateDTO(
                rank=1,
                cell_id="Income_Statement:B15",
                rrf_score=0.95,
                text="Total Revenue: $62,000M",
                matched_subquery="Total Revenue",
            )
        ],
    )
    payload = PgContextExpanderExecutionDTO(
        retrieval_json=retrieval,
        top_k=5,
        adjacent_radius=1,
        max_blocks=10,
    )
    res = module.execute(payload)
    assert "context_blocks" in res
    assert len(res["context_blocks"]) >= 1
    assert any("Total Revenue" in b for b in res["context_blocks"])


def test_v3_workflow_definition_validation(tmp_path):
    repo = AnswerCacheRepository(path=tmp_path / "cache.json")
    registry = ModuleRegistry(repository=repo)
    workflow_store = WorkflowStore(directory=tmp_path / "workflows")
    run_store = MagicMock()
    executor = WorkflowExecutor(registry, workflow_store, run_store)

    workflow_path = Path("data/workflows/default.json")
    assert workflow_path.is_file()
    wf_data = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow = WorkflowDocument.model_validate(wf_data)

    batches = executor.validate_graph(workflow.graph)
    assert len(batches) >= 5
    assert len(workflow.graph.nodes) == 11
    assert len(workflow.graph.edges) == 13
