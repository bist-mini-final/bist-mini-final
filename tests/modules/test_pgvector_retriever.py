from __future__ import annotations

from unittest.mock import MagicMock

from modules.common.base_module import QueryContextDTO
from modules.embedding.query_embedder import EmbeddingsDTO
from modules.retrieval.pgvector_retriever import (
    PgVectorRetrieverConfigDTO,
    PgVectorRetrieverInputDTO,
    PgVectorRetrieverModule,
)
from modules.storage.pgvector_collection_loader import IndexOutputDTO


def test_dense_retrieval_preserves_top_k_per_subquery():
    mock_store = MagicMock()
    doc1 = MagicMock()
    doc1.page_content = "Cell 1 content"
    doc1.metadata = {"cell_id": "cell_1"}
    mock_store.similarity_search_by_vector_with_score.return_value = [(doc1, 0.15)]

    retriever = PgVectorRetrieverModule(pgvector_store=mock_store)

    index_input = IndexOutputDTO(
        index_id="idx_1",
        file_name="samsung.xlsx",
        workbook_hash="hash_1",
        model="text-embedding-3-large",
        dimension=3072,
        document_count=100,
    )
    embeddings = EmbeddingsDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="영업이익"),
        items={"subquery_1": [0.1] * 3072},
    )

    input_dto = PgVectorRetrieverInputDTO(
        query_input=embeddings,
        index_input=index_input,
    )
    res = retriever.execute(input_dto, config=PgVectorRetrieverConfigDTO(top_k=5))

    assert "items" in res
    assert len(res["items"]) == 1
    assert res["items"][0]["cell_id"] == "cell_1"
    assert res["items"][0]["matched_subquery"] == "subquery_1"
    assert res["items"][0]["rank"] == 1
