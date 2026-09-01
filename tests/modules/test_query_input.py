from __future__ import annotations

import pytest
from pydantic import ValidationError

from modules.query.query_input import (
    QueryInputDTO,
    QueryInputModule,
)


def test_query_input_module_execution():
    module = QueryInputModule()
    input_dto = QueryInputDTO(query="삼성전자 2024년 3분기 매출액")
    result = module.execute(input_dto)

    assert "query_context" in result
    query_ctx = result["query_context"]
    assert query_ctx["question_text"] == "삼성전자 2024년 3분기 매출액"
    assert "question_id" in query_ctx
    assert len(query_ctx["question_id"]) > 0


def test_query_input_dto_validation():
    # Empty query should raise ValidationError
    with pytest.raises(ValidationError):
        QueryInputDTO(query="")

    with pytest.raises(ValidationError):
        QueryInputDTO(query="   ")


def test_query_input_carries_external_attachment_sources() -> None:
    result = QueryInputModule().execute(
        QueryInputDTO(
            query="Nexora Labs와 Orbixa를 비교해줘",
            external_context_sources=["SPG_Company_KeyStats_10_orbixa_networks.xlsm"],
        )
    )

    assert result["query_context"]["external_context_sources"] == [
        "SPG_Company_KeyStats_10_orbixa_networks.xlsm"
    ]
