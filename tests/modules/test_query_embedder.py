from __future__ import annotations

from unittest.mock import MagicMock

from modules.common.base_module import QueryContextDTO
from modules.embedding.query_embedder import (
    EmbedderConfigDTO,
    EmbedderInputDTO,
    EmbedderModule,
)
from modules.query.decomposer import SubqueriesDTO, SubqueryItem
from modules.storage.pgvector_collection_loader import IndexOutputDTO


def test_query_embedder_execution():
    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [[0.1] * 1536, [0.2] * 1536]

    embedder = EmbedderModule(encoder=mock_encoder)
    subqueries_dto = SubqueriesDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="삼성전자 매출"),
        items=[
            SubqueryItem(text="subquery 1"),
            SubqueryItem(text="subquery 2"),
        ],
    )
    input_dto = EmbedderInputDTO(
        query_input=subqueries_dto,
        index_input=IndexOutputDTO(
            index_id="idx-test",
            file_name="sample.xlsx",
            workbook_hash="hash",
            model="text-embedding-3-small",
            dimension=1536,
            document_count=2,
        ),
    )
    result = embedder.execute(input_dto, config=EmbedderConfigDTO())

    assert "items" in result
    assert len(result["items"]) == 2
    assert "subquery 1" in result["items"]
    assert len(result["items"]["subquery 1"]) == 1536
    assert result["query_context"]["question_id"] == "q1"
    assert mock_encoder.encode.call_count == 1
    assert embedder.last_model == "text-embedding-3-small"
