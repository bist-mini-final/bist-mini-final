from __future__ import annotations

from unittest.mock import MagicMock

from modules.query.semantic_matcher_engine import QueryExample
from modules.common.base_module import QueryContextDTO
from modules.query.semantic_query_matcher import (
    SemanticQueryMatcherConfig,
    SemanticQueryMatcherInput,
    SemanticQueryMatcherModule,
)


def test_semantic_query_matcher_module_with_mock_encoder():
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
