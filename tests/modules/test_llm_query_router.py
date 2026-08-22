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
        content='{"confidence": 0.95, "items": [{"company_name": "삼성전자", "sheets": ["손익계산서"], "target_topics": ["영업이익"], "matched_score": 1.0, "reason": "삼성전자 손익계산서"}], "reason": "손익계산서 관련 질문"}',
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
    assert res["semantic_match"]["company_name"] == "삼성전자"
    assert len(res["semantic_match"]["items"]) == 1
    assert res["semantic_match"]["items"][0]["company_name"] == "삼성전자"
    assert res["semantic_match"]["items"][0]["sheets"] == ["손익계산서"]
    assert res["semantic_match"]["metrics"]["kind"] == "llm_structured"


def test_llm_query_router_multi_scope_execution():
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"confidence": 0.98, "items": [{"company_name": "삼성전자", "sheets": ["손익계산서"], "target_topics": ["영업이익"]}, {"company_name": "현대자동차", "sheets": ["재무상태표"], "target_topics": ["부채총계"]}], "reason": "다중 기업 비교"}',
        usage={"prompt_tokens": 60, "completion_tokens": 40},
        latency_seconds=0.25,
    )

    router_module = LlmQueryRouterModule(completion_client=mock_llm)
    res = router_module.run(
        LlmQueryRouterInputDTO(
            query_context=QueryContextDTO(
                question_id="q2",
                question_text="삼성전자 2023년 영업이익과 현대자동차 2022년 부채상태를 비교해줘",
            )
        ),
        config=LlmQueryRouterConfigDTO(),
    )

    assert res["semantic_match"]["matched"] is True
    assert len(res["semantic_match"]["items"]) == 2
    assert res["semantic_match"]["items"][0]["company_name"] == "삼성전자"
    assert res["semantic_match"]["items"][1]["company_name"] == "현대자동차"
    assert set(res["semantic_match"]["sheets"]) == {"손익계산서", "재무상태표"}


def test_llm_query_router_preserves_low_model_confidence():
    client = MagicMock()
    client.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"confidence":0.01,"items":[{"company_name":"Unknown","sheets":["IS"]}],"reason":"weak"}',
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
    assert result["semantic_match"]["items"][0]["sheets"] == ["IS"]
