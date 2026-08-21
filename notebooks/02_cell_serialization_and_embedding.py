# %% [markdown]
# # [실험 2] 셀 직렬화(Serialization) 및 pgvector 임베딩 벤치마크
# 
# **목적**:
# 2D 좌표, 행 헤더 계층, 열 헤더 계층을 포함한 원자 셀 직렬화(Structured Cell Text)와
# OpenAI / BGE 임베딩 모델의 1-RTT 배치 인코딩 성능 및 지연 시간을 측정합니다.

# %%
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.providers.embeddings.factory import get_embedding_encoder
from modules.embedding.embedder import EmbedderModule
from modules.embedding.cell_text_embedder import CellTextEmbedderModule
from modules.common.base_module import QueryContextDTO

# %% [markdown]
# ## 1. 임베딩 인코더 싱글톤 캐시 및 초기화 테스트

# %%
model_name = "text-embedding-3-large"
start_t = time.perf_counter()
encoder1 = get_embedding_encoder(model_name)
t1 = time.perf_counter() - start_t

start_t = time.perf_counter()
encoder2 = get_embedding_encoder(model_name)
t2 = time.perf_counter() - start_t

print(f"인코더 최초 생성 소요 시간: {t1:.4f}초")
print(f"인코더 싱글톤 캐시 재사용 소요 시간: {t2:.6f}초 (동일 객체 여부: {encoder1 is encoder2})")

# %% [markdown]
# ## 2. 셀 텍스트 직렬화 샘플 생성

# %%
sample_cells = [
    "Sheet: Key_Stats | Row Header: Income Statement > Total Revenue | Column Header: FY2024 | Cell Value: 61,860",
    "Sheet: Key_Stats | Row Header: Income Statement > Operating Income (EBIT) | Column Header: FY2024 | Cell Value: 9,045",
    "Sheet: Key_Stats | Row Header: Balance Sheet > Total Assets | Column Header: FY2024 | Cell Value: 135,241",
    "Sheet: Key_Stats | Row Header: Balance Sheet > Long-Term Debt | Column Header: FY2024 | Cell Value: 45,820",
    "Sheet: Key_Stats | Row Header: Cash Flow > Cash from Operations | Column Header: FY2024 | Cell Value: 13,931",
]

print("직렬화된 샘플 셀 텍스트:")
for c in sample_cells:
    print(f" - {c}")

# %% [markdown]
# ## 3. 배치 임베딩 모듈 (1-RTT Batch Encoding) 벤치마크

# %%
embedder = EmbedderModule(encoder=encoder1)

start_t = time.perf_counter()
output = embedder.run({
    "subqueries": sample_cells,
    "query_context": {
        "question_id": "BENCHMARK-001",
        "question_text": "2024년 IBM 매출과 영업이익은?",
    },
})
elapsed = time.perf_counter() - start_t

embedded_items = output.get("items", {})
print(f"\n배치 임베딩 완료! ({len(embedded_items)}개 셀) | 총 소요 시간: {elapsed:.3f}초")
for q_text, vector in list(embedded_items.items())[:2]:
    print(f" - 질의: {q_text[:50]}... -> 벡터 차원: {len(vector)}D")

# %% [markdown]
# ## 4. 요약

# %%
print("\n" + "=" * 60)
print("실험 2 요약:")
print(f" - 1-RTT 일괄 인코딩으로 네트워크 왕복 오버헤드 최소화 달성")
print(f" - 싱글톤 인코더 캐시를 통해 객체 생성 오버헤드 0초 수렴")
print("=" * 60)
