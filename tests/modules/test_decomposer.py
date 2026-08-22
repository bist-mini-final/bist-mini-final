from __future__ import annotations

from unittest.mock import MagicMock

from backend.providers.llm.chat_completion import ChatCompletionResult
from modules.common.base_module import QueryContextDTO
from modules.query.decomposer import (
    DecomposerConfigDTO,
    DecomposerInputDTO,
    DecomposerModule,
    SubqueriesDTO,
    SubqueryItem,
)


def test_subquery_item_serialization():
    item = SubqueryItem(
        company="삼성전자",
        sheet="손익계산서",
        row_header="영업이익",
        column_header="2023",
        cell_value="?",
    )
    serialized = item.to_serialized_query()
    assert "Company: 삼성전자" in serialized
    assert "Sheet: 손익계산서" in serialized
    assert "Row Header: 영업이익" in serialized
    assert "Column Header: 2023" in serialized
    assert "Cell Value: ?" in serialized


def test_decomposer_module_execution():
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"items": [{"company": "삼성전자", "sheet": "손익계산서", "row_header": "영업이익", "column_header": "2023", "cell_value": "?"}, {"company": "삼성전자", "sheet": "손익계산서", "row_header": "영업이익", "column_header": "2024", "cell_value": "?"}]}',
        usage={"prompt_tokens": 15, "completion_tokens": 35},
        latency_seconds=0.1,
    )

    module = DecomposerModule(completion_client=mock_llm)
    input_dto = DecomposerInputDTO(
        query_context=QueryContextDTO(
            question_id="q1",
            question_text="삼성전자 2023년 대비 2024년 영업이익 증가율은?",
        )
    )
    result = module.execute(input_dto, config=DecomposerConfigDTO())

    assert "items" in result
    assert len(result["items"]) == 2
    assert result["items"][0]["company"] == "삼성전자"
    assert result["items"][0]["sheet"] == "손익계산서"
    assert result["items"][0]["row_header"] == "영업이익"
    assert result["items"][0]["column_header"] == "2023"
    assert "text" in result["items"][0]
    assert "Company: 삼성전자" in result["items"][0]["text"]

    # Verify SubqueriesDTO model validation and .subqueries helper property
    dto = SubqueriesDTO.model_validate(result)
    assert len(dto.items) == 2
    assert len(dto.subqueries) == 2
    assert "Company: 삼성전자" in dto.subqueries[0]
    assert "2023" in dto.subqueries[0]
    assert "2024" in dto.subqueries[1]
