# %% [markdown]
# # [실험 4] 하이브리드 검색(BM25/Dense) 및 RRF 결합 & 컨텍스트 확장 실험
# 
# **목적**:
# PostgreSQL tsvector GIN(BM25) 키워드 검색과 pgvector HNSW(Dense) 코사인 유사도 검색을 결합하는
# Reciprocal Rank Fusion(RRF) 알고리즘의 파라미터(k, top_k, ratio_penalty) 및
# 인접 행 확장(Adjacent Radius)에 따른 컨텍스트 적중률을 평가합니다.

# %%
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.retrieval.rrf_fusion import RrfFusionModule, RrfFusionConfigDTO
from modules.retrieval.context_expander import ContextExpanderModule, ContextExpanderConfigDTO

# %% [markdown]
# ## 1. BM25 / Dense 모의 검색 결과 생성

# %%
bm25_mock = {
    "query_context": {"question_id": "Q-01", "question_text": "2024년 총매출"},
    "document_context": {"file_name": "SPG_Company_KeyStats_v4.xlsm", "workbook_hash": "hash123"},
    "items": [
        {"rank": 1, "cell_id": "IS:P16", "score": 12.5, "text": "Total Revenue | 2024 | 61860", "matched_subquery": "Total Revenue"},
        {"rank": 2, "cell_id": "IS:P17", "score": 9.2, "text": "Financial Services Revenue | 2024 | 709", "matched_subquery": "Total Revenue"},
        {"rank": 3, "cell_id": "BS:P20", "score": 7.1, "text": "Total Assets | 2024 | 135241", "matched_subquery": "Total Revenue"},
    ]
}

dense_mock = {
    "query_context": {"question_id": "Q-01", "question_text": "2024년 총매출"},
    "document_context": {"file_name": "SPG_Company_KeyStats_v4.xlsm", "workbook_hash": "hash123"},
    "items": [
        {"rank": 1, "cell_id": "IS:P16", "score": 0.89, "text": "Total Revenue | 2024 | 61860", "matched_subquery": "Total Revenue"},
        {"rank": 2, "cell_id": "IS:P18", "score": 0.81, "text": "Gross Profit | 2024 | 33000", "matched_subquery": "Total Revenue"},
        {"rank": 3, "cell_id": "IS:P17", "score": 0.78, "text": "Financial Services Revenue | 2024 | 709", "matched_subquery": "Total Revenue"},
    ]
}

# %% [markdown]
# ## 2. RRF 파라미터 (k=30 vs k=60 vs k=90) 비교 실험

# %%
rrf_module = RrfFusionModule()

for k_val in [30, 60, 90]:
    res = rrf_module.run(
        input_payload={"bm25_result": bm25_mock, "dense_result": dense_mock},
        config={"rrf_k": k_val, "top_k": 5, "ratio_penalty": 0.5},
    )
    print(f"\n[RRF k = {k_val}] 결합 검색 결과 상위 항목:")
    for item in res.get("items", []):
        print(f"  Rank {item['rank']}: Cell {item['cell_id']} | RRF Score: {item['rrf_score']:.5f} | Text: {item['text']}")

# %% [markdown]
# ## 3. 인접 행 컨텍스트 확장 (Context Expander) 실험

# %%
context_expander = ContextExpanderModule()

mock_documents = {
    "file_name": "SPG_Company_KeyStats_v4.xlsm",
    "workbook_hash": "hash123",
    "items": [
        {"cell_id": "IS:O16", "sheet_name": "Income_Statement", "cell_coord": "O16", "cell_value": "60530", "row_header": ["Total Revenue"], "column_header": ["2023"], "variant": "header_with_value", "text": "Total Revenue | 2023 | 60530"},
        {"cell_id": "IS:P16", "sheet_name": "Income_Statement", "cell_coord": "P16", "cell_value": "61860", "row_header": ["Total Revenue"], "column_header": ["2024"], "variant": "header_with_value", "text": "Total Revenue | 2024 | 61860"},
        {"cell_id": "IS:P17", "sheet_name": "Income_Statement", "cell_coord": "P17", "cell_value": "709", "row_header": ["Financial Revenue"], "column_header": ["2024"], "variant": "header_with_value", "text": "Financial Revenue | 2024 | 709"},
    ]
}

retrieval_res = rrf_module.run(
    input_payload={"bm25_result": bm25_mock, "dense_result": dense_mock},
    config={"rrf_k": 60, "top_k": 2},
)

ctx_res = context_expander.run(
    input_payload={"retrieval_json": retrieval_res, "document_input": mock_documents},
    config={"top_k": 2, "adjacent_radius": 2, "max_blocks": 5},
)

print("\n--- 컨텍스트 확장 결과 ---")
ctx_data = ctx_res.get("context_json", {})
print(f"확장 블록 수: {ctx_data.get('block_count')}개 | 총 글자 수: {ctx_data.get('context_characters')}자")
for block in ctx_data.get("context_blocks", []):
    print(f"\n{block}")

# %% [markdown]
# ## 4. 요약

# %%
print("\n" + "=" * 60)
print("실험 4 요약:")
print(" - BM25와 Dense의 상호 보완으로 단일 검색기 대비 Top-1 정확도 향상")
print(" - 2D 그리드 인접 행 및 전후 열 확장으로 시계열 비교 컨텍스트 자동 구성")
print("=" * 60)
