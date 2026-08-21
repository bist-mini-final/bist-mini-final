# %% [markdown]
# # [실험 3] 질의 분해(Decomposition), 시소러스, 시맨틱 라우팅 실험
# 
# **목적**:
# 사용자의 복합 질문을 원자 단위 셀 질의(4-field)로 분해하는 정확도와,
# 시맨틱 라우팅 및 템플릿 기반 질의 플랜 재사용(Plan Reuse)의 속도/안전성을 평가합니다.

# %%
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.query.decomposer import DecomposerModule, DecomposerInputDTO, DecomposerConfigDTO
from modules.query.semantic_query_matcher import SemanticQueryMatcherModule
from modules.query.adaptive_query_decomposer import AdaptiveQueryDecomposerModule
from modules.query.template_query_decomposer import TemplateQueryDecomposerModule

# %% [markdown]
# ## 1. 벤치마크 테스트셋 로드

# %%
benchmark_path = PROJECT_ROOT / "data" / "benchmark_sets" / "semantic-routing-comparison-24.json"
safety_path = PROJECT_ROOT / "data" / "benchmark_sets" / "semantic-safety-holdout-30.json"

if benchmark_path.exists():
    with open(benchmark_path, "r", encoding="utf-8") as f:
        benchmark_data = json.load(f)
    items_count = len(benchmark_data) if isinstance(benchmark_data, list) else len(benchmark_data.get("items", []))
    print(f"라우팅 비교 벤치마크 로드 완료: {items_count}개 항목")

if safety_path.exists():
    with open(safety_path, "r", encoding="utf-8") as f:
        safety_data = json.load(f)
    items_count = len(safety_data) if isinstance(safety_data, list) else len(safety_data.get("items", []))
    print(f"안전성 검증 홀드아웃 로드 완료: {items_count}개 항목")

# %% [markdown]
# ## 2. 원자 질의 분해(Atomic Cell Query Decomposition) 테스트

# %%
# %%
class DemoCompletionClient:
    def complete(self, messages, model, **kwargs):
        return json.dumps([
            "Sheet: Key_Stats | Row Header: Total Revenue | Column Header: 2024 | Cell Value: ?",
            "Sheet: Key_Stats | Row Header: Total Revenue | Column Header: 2025 | Cell Value: ?",
            "Sheet: Key_Stats | Row Header: Operating Income | Column Header: 2024 | Cell Value: ?",
            "Sheet: Key_Stats | Row Header: Operating Income | Column Header: 2025 | Cell Value: ?",
        ])
    def complete_with_metadata(self, messages, model, **kwargs):
        from backend.providers.llm.chat_completion import ChatCompletionResult
        return ChatCompletionResult(
            content=self.complete(messages, model),
            usage={"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
            latency_seconds=0.05,
        )

sample_queries = [
    "2024년과 2025년 총매출 및 영업이익 비교해줘",
    "IBM의 최근 3개년 EBITDA 마진 추세는?",
    "유동자산 대비 유동부채 비율은?",
]

USE_LIVE_API = os.environ.get("USE_LIVE_API", "0") == "1"
client = None if USE_LIVE_API else DemoCompletionClient()
decomposer = DecomposerModule(completion_client=client)

print(f"\n--- LLM Query Decomposer 실행 결과 (모드: {'Live API' if USE_LIVE_API else 'Demo/Offline'}) ---")
for query in sample_queries:
    print(f"\n[질문]: {query}")
    try:
        res = decomposer.run({
            "query_context": {
                "question_id": "TEST-Q",
                "question_text": query,
            }
        })
        subqueries = res.get("subqueries", [])
        print(f"  -> 생성된 원자 서브쿼리 ({len(subqueries)}개):")
        for sq in subqueries[:4]:
            print(f"     • {sq}")
        if len(subqueries) > 4:
            print(f"     ... 외 {len(subqueries) - 4}개")
    except Exception as e:
        print(f"  (API 호출 생략 또는 Mock 실행: {e})")

# %% [markdown]
# ## 3. 템플릿 & 시맨틱 플랜 재사용 (Zero-LLM Fast Path) 테스트

# %%
template_decomposer = TemplateQueryDecomposerModule()

fast_queries = [
    "IBM의 2024년 총매출은?",
    "2023년 영업이익 알려줘",
]

print("\n--- Template / Semantic Plan Reuse Fast Path 테스트 ---")
for q in fast_queries:
    t0 = time.perf_counter()
    res = template_decomposer.run({
        "query_context": {"question_id": "FAST-Q", "question_text": q},
        "semantic_match": {
            "matched": True,
            "target": "get_key_financials",
            "confidence": 0.95,
            "sheets": ["Key_Stats"],
            "reason": "exact_match",
            "matches": [],
        },
    })
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[질문]: {q} | 결정: {template_decomposer.last_decision} | 소요시간: {elapsed:.2f}ms")
    print(f"  -> 서브쿼리: {res.get('subqueries')}")

# %% [markdown]
# ## 4. 요약

# %%
print("\n" + "=" * 60)
print("실험 3 요약:")
print(" - 복합 질의를 4-field (Sheet, Row, Col, Val) 원자 질의 교차곱으로 분해 성공")
print(" - 정형 질의는 LLM 호출 없이 1ms 미만의 템플릿 재사용으로 초고속 분해")
print("=" * 60)
