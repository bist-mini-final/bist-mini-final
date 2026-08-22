from typing import Any, cast
from unittest.mock import MagicMock

from backend.engine.runtime.registry import ModuleRegistry
from backend.providers.llm.chat_completion import ChatCompletionResult
from modules.embedding.query_embedder import EmbedderInputDTO, EmbeddingsDTO
from modules.query.decomposer import DecomposerInputDTO, SubqueriesDTO
from modules.query.query_input import QueryInputDTO
from modules.retrieval.context_expander import DocumentContextDTO
from modules.retrieval.pgvector_retriever import (
    PgVectorRetrieverInputDTO,
    RankedSearchCandidateDTO,
    RankedSearchResultDTO,
)
from modules.retrieval.rrf_fusion import RrfFusionInputDTO
from modules.storage.pgvector_collection_loader import IndexOutputDTO


def test_clean_19_modules_registration():
    registry = ModuleRegistry()
    defs = registry.definitions()
    assert len(defs) == 19


def test_end_to_end_query_reader_pipeline():
    registry = ModuleRegistry()

    # 1. QueryInput
    qi = registry.get("query_input")
    res_qi = qi.run(QueryInputDTO(query="삼성전자 2023년 대비 2024년 영업이익 증가율은?"))
    assert "query_context" in res_qi

    # 2. Decomposer (BaseLLMModule)
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"items": [{"company": "삼성전자", "sheet": "손익계산서", "row_header": "영업이익", "column_header": "2023", "cell_value": "?"}, {"company": "삼성전자", "sheet": "손익계산서", "row_header": "영업이익", "column_header": "2024", "cell_value": "?"}]}',
        usage={"prompt_tokens": 15, "completion_tokens": 35},
        latency_seconds=0.1,
    )
    dec = cast(Any, registry.get("decomposer"))
    dec.completion_client = mock_llm
    res_dec = dec.run(DecomposerInputDTO(query_context=res_qi["query_context"]))
    assert len(res_dec["items"]) == 2

    # 3. Embedder
    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [[0.1] * 3072, [0.2] * 3072]
    embedder = cast(Any, registry.get("embedder"))
    embedder.encoder = mock_encoder
    res_emb = embedder.run(EmbedderInputDTO(query_input=SubqueriesDTO.model_validate(res_dec)))
    assert len(res_emb["items"]) == 2

    # 4. PgVectorRetriever
    retriever = cast(Any, registry.get("pgvector_retriever"))
    mock_store = MagicMock()
    mock_doc = MagicMock()
    mock_doc.page_content = "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670억"
    mock_doc.metadata = {"cell_id": "Samsung:IS:E60"}
    mock_store.similarity_search_by_vector_with_score.return_value = [(mock_doc, 0.1)]
    retriever.pgvector_store = mock_store

    dummy_index = IndexOutputDTO(
        index_id="samsung_2023",
        file_name="samsung.xlsx",
        workbook_hash="hash123",
        model="text-embedding-3-large",
        dimension=3072,
        document_count=1000,
    )
    res_dense = retriever.run(
        PgVectorRetrieverInputDTO(
            query_input=EmbeddingsDTO(query_context=res_qi["query_context"], items=res_emb["items"]),
            index_input=dummy_index,
        )
    )
    assert len(res_dense["items"]) == 2
    assert [item["rank"] for item in res_dense["items"]] == [1, 1]

    # 5. RrfFusion
    rrf = registry.get("rrf_fusion")
    mock_bm25_result = RankedSearchResultDTO(
        query_context=res_qi["query_context"],
        document_context=DocumentContextDTO(
            file_name="samsung.xlsx",
            workbook_hash="hash123",
            index_id="samsung_2023",
        ),
        items=[
            RankedSearchCandidateDTO(
                rank=1,
                cell_id="Samsung:IS:E60",
                score=0.9,
                text=mock_doc.page_content,
                matched_subquery="q1",
            )
        ],
    )
    res_rrf = rrf.run(
        RrfFusionInputDTO(
            bm25_result=mock_bm25_result,
            dense_result=RankedSearchResultDTO.model_validate(res_dense),
        )
    )
    assert len(res_rrf["items"]) == 1

    # 6. PgContextExpander
    pg_expander = cast(Any, registry.get("pg_context_expander"))
    mock_store.fetch_rows_cells.return_value = {
        60: [
            {"col_index": 1, "column_header": ["2023"], "cell_value": "65670억", "cell_coord": "E60", "row_header": ["영업이익"]},
            {"col_index": 2, "column_header": ["2024"], "cell_value": "350000억", "cell_coord": "F60", "row_header": ["영업이익"]},
        ]
    }
    pg_expander.pgvector_store = mock_store
    res_ctx = pg_expander.run({"retrieval_json": res_rrf})
    assert len(res_ctx["context_blocks"]) == 2

    # 7. Integrated Agentic Reader
    mock_reader_llm = MagicMock()
    mock_reader_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content="삼성전자의 2023년 영업이익은 6조 5,670억원이며, 2024년 영업이익은 35조원입니다. 2023년 대비 2024년 영업이익 증가율은 432.97% 증가하였습니다. [Sheet: 손익계산서 | Cell: E60, F60]",
        usage={"prompt_tokens": 80, "completion_tokens": 40},
        latency_seconds=0.2,
    )
    reader = cast(Any, registry.get("reader"))
    reader.completion_client = mock_reader_llm
    reader.pgvector_store = mock_store
    res_reader = reader.run({"context_json": res_ctx})
    assert "432.97%" in res_reader["answer_json"]["answer"]
