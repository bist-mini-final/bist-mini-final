from __future__ import annotations

from unittest.mock import MagicMock

from modules.common.base_module import QueryContextDTO
from modules.embedding.query_embedder import (
    EmbedderConfigDTO,
    EmbedderInputDTO,
    EmbedderModule,
)
from modules.query.decomposer import SubqueriesDTO


def test_query_embedder_execution():
    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [[0.1] * 3072, [0.2] * 3072]

    embedder = EmbedderModule(encoder=mock_encoder)
    subqueries_dto = SubqueriesDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="삼성전자 매출"),
        subqueries=["subquery 1", "subquery 2"],
    )
    input_dto = EmbedderInputDTO(query_input=subqueries_dto)
    result = embedder.execute(input_dto, config=EmbedderConfigDTO(model="text-embedding-3-large"))

    assert "items" in result
    assert len(result["items"]) == 2
    assert "subquery 1" in result["items"]
    assert len(result["items"]["subquery 1"]) == 3072
    assert result["query_context"]["question_id"] == "q1"
