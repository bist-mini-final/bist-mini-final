from typing import Any, cast
from unittest.mock import MagicMock

from backend.engine.runtime.registry import ModuleRegistry
from backend.providers.llm.chat_completion import ChatCompletionResult
from modules.embedding.query_embedder import EmbedderInputDTO, EmbeddingsDTO
from modules.query.decomposer import DecomposerInputDTO, SubqueriesDTO
from modules.query.query_input import QueryInputDTO
from modules.reader.reader import ReaderInputDTO
from modules.retrieval.context_expander import ContextDTO, DocumentContextDTO
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
    assert len(res_dec["subqueries"]) == 2

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


def test_company_entity_extractor():
    registry = ModuleRegistry()
    extractor = cast(Any, registry.get("company_entity_extractor"))
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"company_name": "삼성전자", "ticker": "005930", "display_name": "삼성전자 (005930)", "confidence": "high", "source": "llm"}',
        usage={"prompt_tokens": 50, "completion_tokens": 20},
        latency_seconds=0.1,
    )
    extractor.completion_client = mock_llm
    extractor.catalog = MagicMock()
    extractor.catalog.resolve.return_value = MagicMock()
    extractor._sample_workbook = MagicMock(return_value=["[Sheet1]\n삼성전자 2023 65670"])
    mock_pgvector = MagicMock()
    extractor.pgvector_store = mock_pgvector

    # 1. Standalone execution
    res = extractor.run({"file_name": "samsung_electronics.xlsx", "workbook_hash": "dummy", "sheet_names": ["Sheet1"]})
    assert res["company_name"] == "삼성전자"
    assert res["ticker"] == "005930"
    assert res["display_name"] == "삼성전자 (005930)"

    # 2. Linear Ingestion pipeline with index_input
    mock_idx_id = "idx_" + "a" * 64
    res_with_index = extractor.run({
        "index_input": {
            "index_id": mock_idx_id,
            "file_name": "samsung_electronics.xlsx",
            "workbook_hash": "b" * 64,
            "model": "text-embedding-3-large",
            "dimension": 3072,
            "document_count": 100,
        }
    })
    assert res_with_index["company_name"] == "삼성전자"
    assert res_with_index["index_id"] == mock_idx_id
    mock_pgvector.update_index_company.assert_called_once_with(
        mock_idx_id,
        "삼성전자 (005930)",
    )


def test_postgres_native_keyword_retriever():
    registry = ModuleRegistry()
    retriever = cast(Any, registry.get("postgres_native_keyword_retriever"))
    mock_store = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        ("id-1", "2023 영업이익 65670억", {"cell_id": "c1", "company": "삼성전자"}, 0.85, "uuid-1")
    ]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_store._read_connection.return_value = mock_conn
    retriever.pgvector_store = mock_store

    from modules.common.base_module import QueryContextDTO
    from modules.query.decomposer import DecomposerOutput
    from modules.storage.pgvector_collection_loader import IndexOutputDTO

    res = retriever.run({
        "query_input": DecomposerOutput(
            query_context=QueryContextDTO(question_id="1", question_text="영업이익"),
            subqueries=["Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"]
        ),
        "index_input": IndexOutputDTO(
            index_id="idx_1",
            file_name="samsung.xlsx",
            workbook_hash="hash1",
            model="text-embedding-3-large",
            dimension=3072,
            document_count=100
        )
    })
    assert len(res["items"]) == 1
    assert res["items"][0]["cell_id"] == "c1"


def test_semantic_query_matcher_module_with_mock_encoder():
    from backend.semantic_matching.catalog import QueryExample
    from modules.common.base_module import QueryContextDTO
    from modules.query.semantic_query_matcher import (
        SemanticQueryMatcherConfig,
        SemanticQueryMatcherInput,
        SemanticQueryMatcherModule,
    )

    mock_encoder = MagicMock(spec=["encode"])
    mock_encoder.encode.return_value = [[1.0, 0.0, 0.0]]

    examples = [
        QueryExample(
            example_id="ex-1",
            question="영업이익이 얼마인가요?",
            target="손익계산서",
            sheets=("손익계산서",),
            query_type=1,
        )
    ]

    matcher_module = SemanticQueryMatcherModule(encoder=mock_encoder, examples=examples)
    res = matcher_module.run(
        SemanticQueryMatcherInput(
            query_context=QueryContextDTO(question_id="q1", question_text="영업이익 질문")
        ),
        config=SemanticQueryMatcherConfig(threshold=0.5),
    )

    assert "semantic_match" in res
    assert res["semantic_match"]["matched"] is True
    assert res["semantic_match"]["target"] == "손익계산서"


def test_llm_query_router_module():
    from backend.providers.llm.chat_completion import ChatCompletionResult
    from backend.semantic_matching.catalog import QueryExample
    from modules.common.base_module import QueryContextDTO
    from modules.query.llm_query_router import (
        LlmQueryRouterConfig,
        LlmQueryRouterInput,
        LlmQueryRouterModule,
    )

    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"target": "손익계산서", "company_name": "삼성전자", "company_scopes": [{"raw_mention": "삼성전자", "canonical_name": "삼성전자", "matched_score": 1.0, "target_topics": ["영업이익"], "suggested_sheets": ["손익계산서"]}], "reason": "손익계산서 관련 질문"}',
        usage={"prompt_tokens": 50, "completion_tokens": 30},
        latency_seconds=0.2,
    )

    examples = [
        QueryExample(
            example_id="ex-1",
            question="영업이익이 얼마인가요?",
            target="손익계산서",
            sheets=("손익계산서",),
            query_type=1,
        )
    ]

    router_module = LlmQueryRouterModule(completion_client=mock_llm, examples=examples)
    res = router_module.run(
        LlmQueryRouterInput(
            query_context=QueryContextDTO(question_id="q1", question_text="삼성전자 영업이익")
        ),
        config=LlmQueryRouterConfig(),
    )

    assert "semantic_match" in res
    assert res["semantic_match"]["matched"] is True
    assert res["semantic_match"]["target"] == "손익계산서"
    assert res["semantic_match"]["company_name"] == "삼성전자"
    assert len(res["semantic_match"]["company_scopes"]) == 1
    assert res["semantic_match"]["metrics"]["kind"] == "llm"


def test_reader_tool_calling_execution():
    from modules.common.base_module import DocumentContextDTO, QueryContextDTO
    from modules.reader.reader import ReaderModule

    mock_llm = MagicMock()
    # 1st call returns tool call, 2nd call returns final answer
    mock_llm.complete_with_metadata.side_effect = [
        ChatCompletionResult(
            content="",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            latency_seconds=0.1,
            tool_calls=[
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "lookup_cell_metadata",
                        "arguments": '{"cell_coords": ["B10"], "sheet_name": "손익계산서", "company_name": "삼성전자"}',
                    },
                }
            ],
        ),
        ChatCompletionResult(
            content="삼성전자의 손익계산서 B10 셀의 정확한 영업이익은 65,670억원입니다. [Sheet: 손익계산서 | Cell: B10]",
            usage={"prompt_tokens": 150, "completion_tokens": 30},
            latency_seconds=0.15,
        ),
    ]

    mock_store = MagicMock()
    mock_store.fetch_cells_by_metadata.return_value = [
        {
            "cell_coord": "B10",
            "sheet_name": "손익계산서",
            "company_name": "삼성전자",
            "cell_value": "65,670억원",
            "row_header": ["영업이익"],
            "column_header": ["2023"],
            "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65,670억원",
        }
    ]

    reader = ReaderModule(completion_client=mock_llm, pgvector_store=mock_store)
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(question_id="q1", question_text="삼성전자 2023년 영업이익은?"),
            document_context=DocumentContextDTO(
                file_name="samsung.xlsx",
                workbook_hash="hash123",
                company_name="삼성전자",
                sheet_names=["손익계산서"],
            ),
            top_k_used=5,
            adjacent_radius=2,
            context_characters=100,
            context_blocks=["초안 컨텍스트 데이터"],
        )
    )

    res = reader.execute(input_dto)
    ans = res["answer_json"]["answer"]
    assert "65,670억원" in ans
    assert "[Sheet: 손익계산서 | Cell: B10]" in ans
    assert mock_store.fetch_cells_by_metadata.called


def test_reader_math_tool_calling_execution():
    from modules.common.base_module import DocumentContextDTO, QueryContextDTO
    from modules.reader.reader import ReaderModule, safe_calculate_expression

    assert safe_calculate_expression("(350000 - 65670) / 65670 * 100") == "432.9679"
    assert safe_calculate_expression("round(abs(-12.3456), 2)") == "12.35"
    assert safe_calculate_expression("sum(A, B)", {"A": 10, "B": 20}) == "30"

    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.side_effect = [
        ChatCompletionResult(
            content="",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            latency_seconds=0.1,
            tool_calls=[
                {
                    "id": "call_math_1",
                    "type": "function",
                    "function": {
                        "name": "calculate_math_expression",
                        "arguments": '{"expression": "(350000 - 65670) / 65670 * 100"}',
                    },
                }
            ],
        ),
        ChatCompletionResult(
            content="영업이익 증가율은 432.97% 입니다. [Sheet: 손익계산서 | Cell: E60, F60]",
            usage={"prompt_tokens": 140, "completion_tokens": 25},
            latency_seconds=0.15,
        ),
    ]

    reader = ReaderModule(completion_client=mock_llm)
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(question_id="q2", question_text="영업이익 증가율은?"),
            document_context=DocumentContextDTO(
                file_name="samsung.xlsx",
                workbook_hash="hash123",
                company_name="삼성전자",
                sheet_names=["손익계산서"],
            ),
            top_k_used=5,
            adjacent_radius=2,
            context_characters=100,
            context_blocks=["2023년 영업이익: 65670억, 2024년 영업이익: 350000억"],
        )
    )

    res = reader.execute(input_dto)
    assert "432.97%" in res["answer_json"]["answer"]
