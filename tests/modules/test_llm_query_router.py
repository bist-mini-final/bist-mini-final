from __future__ import annotations

from unittest.mock import MagicMock

from backend.providers.llm.chat_completion import ChatCompletionResult
from modules.common.base_module import QueryContextDTO
from modules.query.llm_query_router import (
    LlmQueryRouterConfigDTO,
    LlmQueryRouterInputDTO,
    LlmQueryRouterModule,
)


def test_llm_query_router_execution():
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"target": "손익계산서", "company_name": "삼성전자", "company_scopes": [{"raw_mention": "삼성전자", "canonical_name": "삼성전자", "matched_score": 1.0, "target_topics": ["영업이익"], "suggested_sheets": ["손익계산서"]}], "reason": "손익계산서 관련 질문"}',
        usage={"prompt_tokens": 50, "completion_tokens": 30},
        latency_seconds=0.2,
    )

    router_module = LlmQueryRouterModule(completion_client=mock_llm)
    res = router_module.run(
        LlmQueryRouterInputDTO(
            query_context=QueryContextDTO(question_id="q1", question_text="삼성전자 영업이익")
        ),
        config=LlmQueryRouterConfigDTO(),
    )

    assert "semantic_match" in res
    assert res["semantic_match"]["matched"] is True
    assert res["semantic_match"]["target"] == "손익계산서"
    assert res["semantic_match"]["company_name"] == "삼성전자"
    assert len(res["semantic_match"]["company_scopes"]) == 1
    assert res["semantic_match"]["metrics"]["kind"] == "llm_structured"


def test_llm_query_router_preserves_low_model_confidence():
    client = MagicMock()
    client.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"target":"IS","confidence":0.01,"company_name":null,"company_scopes":[],"reason":"weak"}',
        usage={},
        latency_seconds=0,
    )
    module = LlmQueryRouterModule(completion_client=client)
    result = module.run(
        LlmQueryRouterInputDTO(
            query_context=QueryContextDTO(question_id="q", question_text="maybe revenue")
        )
    )

    assert result["semantic_match"]["matched"] is True
    assert result["semantic_match"]["target"] == "IS"
