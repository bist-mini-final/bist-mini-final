"""Generator script to produce 19 individual Jupyter notebooks in notebooks/modules/ (1 notebook per module)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

NOTEBOOKS_DIR = Path("/Users/pileuszu/Repos/bist-mini-final/notebooks/modules")


def make_notebook(cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3 (bist-mini-final)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.11.0",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 4,
    }


def md_cell(source: str) -> Dict[str, Any]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in source.strip().split("\n")],
    }


def code_cell(source: str) -> Dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in source.strip().split("\n")],
    }


COMMON_SETUP_CELL = code_cell("""import sys
from pathlib import Path
import json

# 프로젝트 루트 경로 등록
PROJECT_ROOT = Path(".").resolve().parent.parent if Path(".").resolve().name == "modules" else Path(".").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def print_io(title: str, input_data: dict, output_data: dict):
    print("=" * 70)
    print(f"📌 [Module Execution] {title}")
    print("=" * 70)
    print("\\n📥 [Input DTO]")
    print(json.dumps(input_data, indent=2, ensure_ascii=False))
    print("\\n📤 [Output Result]")
    print(json.dumps(output_data, indent=2, ensure_ascii=False))
    print("\\n")
""")


# ==============================================================================
# Individual Module Notebook Builders (1 to 19)
# ==============================================================================

# 1. query_input
def nb_query_input() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `query_input` (QueryInputModule)
- **Category**: Source
- **Role**: 자연어 질문 문자열을 수신하여 전체 파이프라인에서 공유되는 고유 `question_id`와 `QueryContextDTO`를 생성합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.query.query_input import QueryInputModule, QueryInputDTO

# 1. 모듈 인스턴스화
module = QueryInputModule()

# 2. 샘플 입력 데이터 구성
sample_input = {
    "query": "2023년 삼성전자 영업이익과 2022년 대비 증감율은 얼마인가요?"
}
input_dto = QueryInputDTO(**sample_input)

# 3. 모듈 실행
output = module.run(input_dto)
print_io("query_input (QueryInputModule)", sample_input, output)
"""),
    ])


# 2. decomposer
def nb_decomposer() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `decomposer` (DecomposerModule)
- **Category**: Logic (LLM)
- **Role**: 복합 자연어 질문을 각 시점 및 계정 항목 단위의 정형 서브쿼리(`Company: ... | Sheet: ... | Row Header: ... | Column Header: ... | Cell Value: ?`)로 분해합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.query.decomposer import DecomposerModule, DecomposerInputDTO, DecomposerConfigDTO
from backend.providers.llm.chat_completion import ChatCompletionResult

# Mock LLM Client (OpenAI API 키 없이도 결정론적 테스트 가능)
mock_llm = MagicMock()
mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
    content=json.dumps({
        "items": [
            {
                "company": "삼성전자",
                "sheet": "손익계산서",
                "row_header": "영업이익",
                "column_header": "2022",
                "cell_value": "?"
            },
            {
                "company": "삼성전자",
                "sheet": "손익계산서",
                "row_header": "영업이익",
                "column_header": "2023",
                "cell_value": "?"
            }
        ]
    }),
    usage={"prompt_tokens": 45, "completion_tokens": 60, "total_tokens": 105},
    latency_seconds=0.35,
)

module = DecomposerModule(completion_client=mock_llm)

sample_input = {
    "query_context": {
        "question_id": "QUERY-001",
        "question_text": "2023년 삼성전자 영업이익과 2022년 대비 증감율은 얼마인가요?"
    }
}
input_dto = DecomposerInputDTO(**sample_input)
output = module.run(input_dto, config=DecomposerConfigDTO(model="gpt-5.6-luna"))
print_io("decomposer (DecomposerModule)", sample_input, output)
"""),
    ])


# 3. llm_query_router
def nb_llm_query_router() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `llm_query_router` (LlmQueryRouterModule)
- **Category**: Logic (LLM)
- **Role**: 질문 의도를 파악하여 연관 기업명과 대상 재무제표 시트명(손익계산서, 재무상태표, 현금흐름표 등)을 사전 라우팅합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.query.llm_query_router import LlmQueryRouterModule, LlmQueryRouterInputDTO, LlmQueryRouterConfigDTO
from backend.providers.llm.chat_completion import ChatCompletionResult

mock_router_llm = MagicMock()
mock_router_llm.complete_with_metadata.return_value = ChatCompletionResult(
    content=json.dumps({
        "matched": True,
        "company_name": "삼성전자",
        "sheets": ["손익계산서", "포괄손익계산서"],
        "confidence": 0.95,
        "reasoning": "영업이익 및 수익성 지표는 손익계산서 시트에 위치합니다."
    }),
    usage={"prompt_tokens": 30, "completion_tokens": 40, "total_tokens": 70},
    latency_seconds=0.22,
)

module = LlmQueryRouterModule(completion_client=mock_router_llm)

sample_input = {
    "query_context": {
        "question_id": "QUERY-001",
        "question_text": "삼성전자 손익계산서에서 영업이익 조회해줘"
    }
}
input_dto = LlmQueryRouterInputDTO(**sample_input)
output = module.run(input_dto, config=LlmQueryRouterConfigDTO(model="gpt-5.6-luna"))
print_io("llm_query_router (LlmQueryRouterModule)", sample_input, output)
"""),
    ])


# 4. semantic_query_matcher
def nb_semantic_query_matcher() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `semantic_query_matcher` (SemanticQueryMatcherModule)
- **Category**: Logic (Embedding)
- **Role**: 질문 텍스트와 쿼리 뱅크 예제 간 코사인 유사도를 계산하여 대상 시트/기업을 매칭합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.query.semantic_query_matcher import (
    SemanticQueryMatcherModule,
    SemanticQueryMatcherInput,
    SemanticQueryMatcherConfig,
    QueryExample,
)

mock_encoder = MagicMock()
mock_encoder.model_name = "text-embedding-3-large"
mock_encoder.encode.return_value = [[0.05] * 3072]

examples = [
    QueryExample(example_id="ex1", question="삼성전자 영업이익", target="손익계산서", sheets=("손익계산서",))
]
module = SemanticQueryMatcherModule(encoder=mock_encoder, examples=examples)

sample_input = {
    "query_context": {
        "question_id": "QUERY-001",
        "question_text": "삼성전자 2023년 영업이익"
    }
}
input_dto = SemanticQueryMatcherInput(**sample_input)
output = module.run(input_dto, config=SemanticQueryMatcherConfig(threshold=0.7))
print_io("semantic_query_matcher (SemanticQueryMatcherModule)", sample_input, output)
"""),
    ])


# 5. embedder (Query Embedder)
def nb_embedder() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `embedder` (EmbedderModule)
- **Category**: Logic (Embedding)
- **Role**: 분해된 서브쿼리 리스트(`SubqueriesDTO`)를 3072차원 고차원 밀집 벡터 딕셔너리로 일괄 인코딩합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.embedding.query_embedder import EmbedderModule, EmbedderInputDTO, EmbedderConfigDTO

mock_encoder = MagicMock()
mock_encoder.model_name = "text-embedding-3-large"
mock_encoder.dimension = 3072
mock_encoder.encode.return_value = [
    [0.0123, -0.0456, 0.0789] + [0.0] * 3069,
    [-0.0321, 0.0654, -0.0987] + [0.0] * 3069
]

module = EmbedderModule(encoder=mock_encoder)

sample_input = {
    "query_input": {
        "query_context": {
            "question_id": "QUERY-001",
            "question_text": "2023년 삼성전자 영업이익과 2022년 대비 증감율"
        },
        "items": [
            {
                "company": "삼성전자",
                "sheet": "손익계산서",
                "row_header": "영업이익",
                "column_header": "2022",
                "cell_value": "?"
            },
            {
                "company": "삼성전자",
                "sheet": "손익계산서",
                "row_header": "영업이익",
                "column_header": "2023",
                "cell_value": "?"
            }
        ]
    }
}
input_dto = EmbedderInputDTO(**sample_input)
output = module.run(input_dto, config=EmbedderConfigDTO(model="text-embedding-3-large", dimension=3072))

summary_output = {
    "query_context": output["query_context"],
    "items": {
        q: {"dimension": len(vec), "preview": vec[:3]}
        for q, vec in output["items"].items()
    }
}
print_io("embedder (EmbedderModule)", sample_input, summary_output)
"""),
    ])


# 6. cell_text_embedder
def nb_cell_text_embedder() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `cell_text_embedder` (CellTextEmbedderModule)
- **Category**: Logic (Embedding)
- **Role**: 엑셀 직렬화 셀 텍스트 목록을 고속 배치 임베딩하고 아티팩트 저장소에 저장합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.embedding.cell_text_embedder import CellTextEmbedderModule, CellTextEmbedderInputDTO, CellTextEmbedderConfigDTO

mock_encoder = MagicMock()
mock_encoder.model_name = "text-embedding-3-large"
mock_encoder.dimension = 3072
mock_encoder.embed_documents.return_value = [[0.011] * 3072, [0.022] * 3072]
mock_encoder.encode.return_value = [[0.011] * 3072, [0.022] * 3072]

artifact_store = MagicMock()
artifact_store.is_valid.return_value = False
artifact_store.put_streaming.return_value = None

module = CellTextEmbedderModule(encoder=mock_encoder, artifact_store=artifact_store)

sample_input = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "hash_samsung_2023",
    "company_name": "삼성전자",
    "items": [
        {
            "cell_id": "삼성전자:IS:C5",
            "sheet_name": "손익계산서",
            "cell_coord": "C5",
            "row_header": ["영업이익"],
            "column_header": ["2022"],
            "cell_value": "433766",
            "variant": "header_with_value",
            "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: 433766"
        },
        {
            "cell_id": "삼성전자:IS:D5",
            "sheet_name": "손익계산서",
            "cell_coord": "D5",
            "row_header": ["영업이익"],
            "column_header": ["2023"],
            "cell_value": "65670",
            "variant": "header_with_value",
            "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
        }
    ]
}
input_dto = CellTextEmbedderInputDTO(**sample_input)
output = module.run(input_dto, config=CellTextEmbedderConfigDTO(batch_size=512))
print_io("cell_text_embedder (CellTextEmbedderModule)", sample_input, output)
"""),
    ])


# 7. processed_file_selector
def nb_processed_file_selector() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `processed_file_selector` (ProcessedFileSelectorModule)
- **Category**: Source
- **Role**: 인제스천할 원본 엑셀 파일을 선택하고 파일 해시 및 시트 유효성을 검증합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.storage.processed_file_selector import ProcessedFileSelectorModule, ProcessedFileSelectorInputDTO

sample_input = {
    "file_name": "samsung_2023.xlsx",
    "sheet_names": ["손익계산서", "재무상태표"]
}

mock_selector_output = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "a1b2c3d4e5f67890",
    "company_name": "삼성전자",
    "sheet_names": ["손익계산서", "재무상태표"],
    "total_sheets": 2
}
print_io("processed_file_selector (ProcessedFileSelectorModule)", sample_input, mock_selector_output)
"""),
    ])


# 8. luna_vlm_structure_detector
def nb_luna_vlm_structure_detector() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `luna_vlm_structure_detector` (LunaVlmStructureDetectorModule)
- **Category**: Logic (VLM)
- **Role**: Luna VLM 멀티모달 모델을 통해 복잡한 시트 내 표 영역(Region), 복합 계층 행 헤더 및 열 헤더를 자동 감지합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.structure.luna_vlm_structure_detector import LunaVlmStructureDetectorModule, LunaVlmStructureDetectorInputDTO

sample_input = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "a1b2c3d4e5f67890",
    "company_name": "삼성전자",
    "sheet_names": ["손익계산서"]
}

mock_structure_output = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "a1b2c3d4e5f67890",
    "company_name": "삼성전자",
    "sheet_names": ["손익계산서"],
    "tables": [
        {
            "sheet_name": "손익계산서",
            "table_index": 0,
            "region": {"start_row": 3, "end_row": 50, "start_col": 1, "end_col": 6},
            "header_rows": [3, 4],
            "header_columns": [1, 2],
            "title": "연결 손익계산서"
        }
    ]
}
print_io("luna_vlm_structure_detector (LunaVlmStructureDetectorModule)", sample_input, mock_structure_output)
"""),
    ])


# 9. cell_text_serializer
def nb_cell_text_serializer() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `cell_text_serializer` (CellTextSerializerModule)
- **Category**: Transform
- **Role**: 감지된 표 구조와 셀 원본 데이터를 결합하여 검색에 최적화된 표준화 다큐먼트 텍스트(`Company: ... | Sheet: ... | Row Header: ... | Column Header: ... | Cell Value: ...`)로 직렬화합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.structure.cell_text_serializer import CellTextSerializerModule, CellTextSerializerInputDTO

sample_input = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "a1b2c3d4e5f67890",
    "company_name": "삼성전자",
    "sheet_names": ["손익계산서"],
    "tables": [
        {
            "sheet_name": "손익계산서",
            "table_index": 0,
            "region": {"start_row": 3, "end_row": 50, "start_col": 1, "end_col": 6},
            "header_rows": [3, 4],
            "header_columns": [1, 2],
            "title": "연결 손익계산서"
        }
    ]
}

mock_serializer_output = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "a1b2c3d4e5f67890",
    "company_name": "삼성전자",
    "items": [
        {
            "cell_id": "삼성전자:손익계산서:C5",
            "sheet_name": "손익계산서",
            "cell_coord": "C5",
            "row_header": ["영업이익"],
            "column_header": ["2022"],
            "cell_value": "433766",
            "variant": "header_with_value",
            "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: 433766"
        },
        {
            "cell_id": "삼성전자:손익계산서:D5",
            "sheet_name": "손익계산서",
            "cell_coord": "D5",
            "row_header": ["영업이익"],
            "column_header": ["2023"],
            "cell_value": "65670",
            "variant": "header_with_value",
            "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
        }
    ]
}
print_io("cell_text_serializer (CellTextSerializerModule)", sample_input, mock_serializer_output)
"""),
    ])


# 10. pgvector_collection_loader
def nb_pgvector_collection_loader() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `pgvector_collection_loader` (PgVectorCollectionLoaderModule)
- **Category**: Source
- **Role**: PostgreSQL pgvector에 저장된 인덱스 컬렉션 메타데이터를 조회하여 검색 단계로 전달합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.storage.pgvector_collection_loader import PgVectorCollectionLoaderModule, PgVectorCollectionLoaderInputDTO

mock_pg_store = MagicMock()
mock_pg_store.list_indexes.return_value = [
    {
        "index_id": "idx_samsung_2023",
        "file_name": "samsung_2023.xlsx",
        "workbook_hash": "hash_samsung_2023",
        "model": "text-embedding-3-large",
        "dimension": 3072,
        "document_count": 1520,
    }
]
mock_pg_store.get_document_count.return_value = 1520
mock_pg_store.fetch_source_documents.return_value = []

module = PgVectorCollectionLoaderModule(pgvector_store=mock_pg_store)

sample_input = {
    "collection_name": "samsung_2023.xlsx",
    "collection_names": ["samsung_2023.xlsx"]
}
input_dto = PgVectorCollectionLoaderInputDTO(**sample_input)
output = module.run(input_dto)
print_io("pgvector_collection_loader (PgVectorCollectionLoaderModule)", sample_input, output)
"""),
    ])


# 11. pgvector_index_writer
def nb_pgvector_index_writer() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `pgvector_index_writer` (PgVectorIndexWriterModule)
- **Category**: Storage / DB
- **Role**: 임베딩된 셀 벡터 및 원본 메타데이터를 PostgreSQL pgvector에 COPY 바이너리로 고속 적재하고 HNSW 인덱스를 생성합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.storage.pgvector_index_writer import PgVectorIndexWriterModule, PgVectorIndexWriterInputDTO

sample_input = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "hash_samsung_2023",
    "company_name": "삼성전자",
    "model": "text-embedding-3-large",
    "dimension": 3072,
    "artifact_id": "artifact_samsung_2023",
    "document_count": 1520
}

mock_writer_output = {
    "index_id": "idx_samsung_2023",
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "hash_samsung_2023",
    "model": "text-embedding-3-large",
    "dimension": 3072,
    "document_count": 1520
}
print_io("pgvector_index_writer (PgVectorIndexWriterModule)", sample_input, mock_writer_output)
"""),
    ])


# 12. pgvector_retriever
def nb_pgvector_retriever() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `pgvector_retriever` (PgVectorRetrieverModule)
- **Category**: Logic (Dense Retrieval)
- **Role**: 서브쿼리 임베딩 벡터와 pgvector 인덱스 간 코사인 유사도를 계산하여 Top-K 밀집 검색 후보를 반환합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.retrieval.pgvector_retriever import PgVectorRetrieverModule, PgVectorRetrieverInputDTO, PgVectorRetrieverConfigDTO

mock_store = MagicMock()
mock_doc = MagicMock()
mock_doc.page_content = "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
mock_doc.metadata = {"cell_id": "삼성전자:손익계산서:D5"}
mock_store.similarity_search_by_vector_with_score.return_value = [(mock_doc, 0.05)]

module = PgVectorRetrieverModule(pgvector_store=mock_store)

sample_input = {
    "query_input": {
        "query_context": {"question_id": "QUERY-001", "question_text": "2023년 삼성전자 영업이익"},
        "items": {
            "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?": [0.05] * 3072
        }
    },
    "index_input": {
        "index_id": "idx_samsung_2023",
        "file_name": "samsung_2023.xlsx",
        "workbook_hash": "hash_samsung_2023",
        "model": "text-embedding-3-large",
        "dimension": 3072,
        "document_count": 1000
    }
}
input_dto = PgVectorRetrieverInputDTO(**sample_input)
output = module.run(input_dto, config=PgVectorRetrieverConfigDTO(top_k=5))
print_io("pgvector_retriever (PgVectorRetrieverModule)", sample_input, output)
"""),
    ])


# 13. postgres_native_keyword_retriever
def nb_postgres_native_keyword_retriever() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `postgres_native_keyword_retriever` (PostgresNativeKeywordRetrieverModule)
- **Category**: Logic (Sparse / BM25 FTS)
- **Role**: PostgreSQL Full-Text Search(FTS) 인덱스를 사용하여 어휘적 일치(Exact Match / BM25) 상위 후보 셀을 검색합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.retrieval.postgres_native_keyword_retriever import (
    PostgresNativeKeywordRetrieverModule,
    PostgresNativeKeywordRetrieverInputDTO,
)

sample_input = {
    "query_input": {
        "query_context": {"question_id": "QUERY-001", "question_text": "2023년 삼성전자 영업이익"},
        "items": [
            {
                "company": "삼성전자",
                "sheet": "손익계산서",
                "row_header": "영업이익",
                "column_header": "2023",
                "cell_value": "?"
            }
        ]
    },
    "index_input": {
        "index_id": "idx_samsung_2023",
        "file_name": "samsung_2023.xlsx",
        "workbook_hash": "hash_samsung_2023",
        "model": "text-embedding-3-large",
        "dimension": 3072,
        "document_count": 1000
    }
}

mock_bm25_output = {
    "query_context": {"question_id": "QUERY-001", "question_text": "2023년 삼성전자 영업이익"},
    "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "hash_samsung_2023", "index_id": "idx_samsung_2023"},
    "items": [
        {
            "rank": 1,
            "cell_id": "삼성전자:손익계산서:D5",
            "score": 0.88,
            "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
            "matched_subquery": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
        }
    ]
}
print_io("postgres_native_keyword_retriever (PostgresNativeKeywordRetrieverModule)", sample_input, mock_bm25_output)
"""),
    ])


# 14. rrf_fusion
def nb_rrf_fusion() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `rrf_fusion` (RrfFusionModule)
- **Category**: Logic (Fusion)
- **Role**: Dense 검색 결과와 Sparse(BM25) 검색 결과를 RRF(Reciprocal Rank Fusion) 공식 ($score = \\sum \\frac{1}{k + rank}$)으로 결합하여 단일 최적 순위 목록을 산출합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.retrieval.rrf_fusion import RrfFusionModule, RrfFusionInputDTO, RrfFusionConfigDTO

module = RrfFusionModule()

sample_input = {
    "dense_result": {
        "query_context": {"question_id": "QUERY-001", "question_text": "2023년 삼성전자 영업이익"},
        "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "hash_samsung_2023", "index_id": "idx_samsung_2023"},
        "items": [
            {
                "rank": 1,
                "cell_id": "삼성전자:손익계산서:D5",
                "score": 0.95,
                "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
                "matched_subquery": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
            }
        ]
    },
    "bm25_result": {
        "query_context": {"question_id": "QUERY-001", "question_text": "2023년 삼성전자 영업이익"},
        "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "hash_samsung_2023", "index_id": "idx_samsung_2023"},
        "items": [
            {
                "rank": 1,
                "cell_id": "삼성전자:손익계산서:D5",
                "score": 0.88,
                "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
                "matched_subquery": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
            }
        ]
    }
}
input_dto = RrfFusionInputDTO(**sample_input)
output = module.run(input_dto, config=RrfFusionConfigDTO(top_k=5, rrf_k=60))
print_io("rrf_fusion (RrfFusionModule)", sample_input, output)
"""),
    ])


# 15. context_expander (pg_context_expander)
def nb_context_expander() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `pg_context_expander` (PgContextExpanderModule)
- **Category**: Logic (Context Expansion)
- **Role**: RRF 상위 후보 셀이 위치한 행(Row)의 전체 열(Columns: 시계열 연도별 셀 전체)을 PostgreSQL에서 일괄 조회하여 온전한 원본 다큐먼트 문자열 리스트(`items: List[str]`)로 확장 복원합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.retrieval.context_expander import PgContextExpanderModule, PgContextExpanderInputDTO, PgContextExpanderConfigDTO

mock_pg_store = MagicMock()
mock_pg_store.fetch_rows_cells.return_value = {
    5: [
        {
            "col_index": 1,
            "column_header": ["2021"],
            "cell_value": "516339",
            "cell_coord": "B5",
            "row_header": ["영업이익"],
            "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2021 | Cell Value: 516339"
        },
        {
            "col_index": 2,
            "column_header": ["2022"],
            "cell_value": "433766",
            "cell_coord": "C5",
            "row_header": ["영업이익"],
            "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: 433766"
        },
        {
            "col_index": 3,
            "column_header": ["2023"],
            "cell_value": "65670",
            "cell_coord": "D5",
            "row_header": ["영업이익"],
            "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
        }
    ]
}

module = PgContextExpanderModule(pgvector_store=mock_pg_store)

sample_input = {
    "retrieval_json": {
        "query_context": {"question_id": "QUERY-001", "question_text": "2023년 삼성전자 영업이익"},
        "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "hash_samsung_2023", "index_id": "idx_samsung_2023"},
        "items": [
            {
                "rank": 1,
                "cell_id": "삼성전자:손익계산서:D5",
                "rrf_score": 0.0327,
                "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
                "matched_subquery": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
            }
        ]
    }
}
input_dto = PgContextExpanderInputDTO(**sample_input)
output = module.run(input_dto, config=PgContextExpanderConfigDTO(top_k=5, max_blocks=100))
print_io("pg_context_expander (PgContextExpanderModule)", sample_input, output)
"""),
    ])


# 16. reader
def nb_reader() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `reader` (ReaderModule)
- **Category**: Output (Agentic LLM)
- **Role**: 확장된 원본 셀 다큐먼트 리스트를 프롬프트에 주입하고, LangChain BaseTool 기반 수학 계산 및 메타데이터 조회 도구를 결합하여 환각 없는 최종 답변을 합성합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from unittest.mock import MagicMock
from modules.reader.reader import ReaderModule, ReaderInputDTO, ReaderConfigDTO
from backend.providers.llm.chat_completion import ChatCompletionResult

mock_reader_llm = MagicMock()
mock_reader_llm.complete_with_metadata.return_value = ChatCompletionResult(
    content="2023년 삼성전자의 영업이익은 65,670억원이며, 2022년(433,766억원) 대비 약 84.86% 감소하였습니다. [Sheet: 손익계산서 | Cell: C5, D5]",
    usage={"prompt_tokens": 320, "completion_tokens": 75, "total_tokens": 395},
    latency_seconds=1.12,
)

module = ReaderModule(completion_client=mock_reader_llm)

sample_input = {
    "context_json": {
        "query_context": {
            "question_id": "QUERY-001",
            "question_text": "2023년 삼성전자 영업이익과 2022년 대비 증감율은 얼마인가요?"
        },
        "document_context": {
            "file_name": "samsung_2023.xlsx",
            "workbook_hash": "hash_samsung_2023"
        },
        "items": [
            "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2021 | Cell Value: 516339",
            "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: 433766",
            "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
        ]
    }
}
input_dto = ReaderInputDTO(**sample_input)
output = module.run(input_dto, config=ReaderConfigDTO(model="gpt-5.6-luna", enable_tools=True))
print_io("reader (ReaderModule)", sample_input, output)
"""),
    ])


# 17. company_entity_extractor
def nb_company_entity_extractor() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `company_entity_extractor` (CompanyEntityExtractorModule)
- **Category**: Storage / DB
- **Role**: 엑셀 워크북 파일명 및 시트 메타데이터에서 기업명, 종목 코드, 회계연도 엔티티를 추출하여 DB에 영속화합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.storage.company_entity_extractor import CompanyEntityExtractorModule, CompanyEntityExtractorInputDTO

sample_input = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "hash_samsung_2023"
}

mock_entity_output = {
    "company_name": "삼성전자",
    "stock_code": "005930",
    "fiscal_years": [2021, 2022, 2023],
    "industry": "반도체 및 전자제품 제조업",
    "registered_sheets": ["손익계산서", "재무상태표", "현금흐름표"]
}
print_io("company_entity_extractor (CompanyEntityExtractorModule)", sample_input, mock_entity_output)
"""),
    ])


# 18. sheet_metadata_persistence
def nb_sheet_metadata_persistence() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `sheet_metadata_persistence` (SheetMetadataPersistenceModule)
- **Category**: Storage / DB
- **Role**: 시트별 행/열 개수, 표 구조 스키마 및 인덱스 상태 메타데이터를 PostgreSQL에 영속화합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.storage.sheet_metadata_persistence import SheetMetadataPersistenceModule, SheetMetadataPersistenceInputDTO

sample_input = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "hash_samsung_2023",
    "sheet_names": ["손익계산서", "재무상태표"]
}

mock_sheet_output = {
    "file_name": "samsung_2023.xlsx",
    "workbook_hash": "hash_samsung_2023",
    "persisted_sheets_count": 2,
    "status": "SUCCESS"
}
print_io("sheet_metadata_persistence (SheetMetadataPersistenceModule)", sample_input, mock_sheet_output)
"""),
    ])


# 19. qa_example_loader
def nb_qa_example_loader() -> Dict[str, Any]:
    return make_notebook([
        md_cell("""# `qa_example_loader` (QaExampleLoaderModule)
- **Category**: Source
- **Role**: 평가 및 퓨샷 쿼리 뱅크용 도메인 QA 예제 데이터셋을 로드합니다.
"""),
        COMMON_SETUP_CELL,
        code_cell("""from modules.storage.qa_example_loader import (
    QaExampleLoaderModule,
    QaExampleLoaderInputDTO,
    QaExampleLoaderConfigDTO,
)

sample_input = {
    "file_name": None
}
input_dto = QaExampleLoaderInputDTO(**sample_input)
module = QaExampleLoaderModule()
output = module.run(input_dto, config=QaExampleLoaderConfigDTO(include_builtin=True))
print_io("qa_example_loader (QaExampleLoaderModule)", sample_input, output)
"""),
    ])


def main():
    # Remove existing files in notebooks/modules/
    if NOTEBOOKS_DIR.exists():
        shutil.rmtree(NOTEBOOKS_DIR)
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)

    modules_map = {
        "01_query_input.ipynb": nb_query_input(),
        "02_decomposer.ipynb": nb_decomposer(),
        "03_llm_query_router.ipynb": nb_llm_query_router(),
        "04_semantic_query_matcher.ipynb": nb_semantic_query_matcher(),
        "05_embedder.ipynb": nb_embedder(),
        "06_cell_text_embedder.ipynb": nb_cell_text_embedder(),
        "07_processed_file_selector.ipynb": nb_processed_file_selector(),
        "08_luna_vlm_structure_detector.ipynb": nb_luna_vlm_structure_detector(),
        "09_cell_text_serializer.ipynb": nb_cell_text_serializer(),
        "10_pgvector_collection_loader.ipynb": nb_pgvector_collection_loader(),
        "11_pgvector_index_writer.ipynb": nb_pgvector_index_writer(),
        "12_pgvector_retriever.ipynb": nb_pgvector_retriever(),
        "13_postgres_native_keyword_retriever.ipynb": nb_postgres_native_keyword_retriever(),
        "14_rrf_fusion.ipynb": nb_rrf_fusion(),
        "15_context_expander.ipynb": nb_context_expander(),
        "16_reader.ipynb": nb_reader(),
        "17_company_entity_extractor.ipynb": nb_company_entity_extractor(),
        "18_sheet_metadata_persistence.ipynb": nb_sheet_metadata_persistence(),
        "19_qa_example_loader.ipynb": nb_qa_example_loader(),
    }

    for filename, nb_dict in modules_map.items():
        filepath = NOTEBOOKS_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(nb_dict, f, indent=1, ensure_ascii=False)
        print(f"✅ Generated 1:1 notebook: {filepath.name}")

    print(f"\n🎉 총 {len(modules_map)}개의 1:1 모듈 주피터 노트북 생성 완료!")


if __name__ == "__main__":
    main()
