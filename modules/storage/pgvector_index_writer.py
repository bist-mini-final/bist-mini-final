"""셀 텍스트 임베딩 벡터와 셀 메타데이터를 PostgreSQL 16 pgvector HNSW 인덱스 테이블에 영구 적재하는 모듈.

CellTextEmbedder에서 생성된 부동소수점 임베딩 아티팩트와 원본 엑셀 셀 정보를 결합하여
고속 바이너리 복사(COPY) 및 트랜잭션 단위로 pgvector 테이블에 벌크 삽입(bulk insert)합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "file_name": "samsung_2023_financials.xlsx",
      "workbook_hash": "a1b2c3d4...",
      "model": "text-embedding-3-large",
      "dimension": 3072,
      "embedding_artifact_path": "data/artifacts/embeddings/a1b2c3d4.bin",
      "items": [
        {
          "sheet_name": "손익계산서",
          "row_index": 5,
          "column_index": 2,
          "cell_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
        }
      ]
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "index_id": "idx_a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890",
      "file_name": "samsung_2023_financials.xlsx",
      "workbook_hash": "a1b2c3d4...",
      "model": "text-embedding-3-large",
      "dimension": 3072,
      "document_count": 1250
    }
    ```
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field

from backend.core.settings import PROCESSED_DATA_DIR
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PGVECTOR_INSERT_BATCH_SIZE, PgVectorStore
from backend.storage.spreadsheets.langchain_document import lazy_cell_documents
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleTaskPolicy,
)
from modules.embedding.cell_text_embedder import CellTextEmbeddingsDTO

logger = logging.getLogger(__name__)


class VectorIndexDTO(ModuleDTO):
    index_id: str = Field(
        pattern=r"^idx_[a-f0-9]{64}$",
        description="영속 벡터 인덱스의 콘텐츠 주소",
    )
    file_name: str = Field(description="인덱싱한 원본 Excel 파일명")
    workbook_hash: str = Field(description="인덱싱한 Excel 파일 해시")
    model: str = Field(description="문서 임베딩 모델 ID")
    dimension: int = Field(gt=0, description="벡터 차원")
    document_count: int = Field(gt=0, description="저장된 검색 문서 개수")


class PgVectorIndexWriterInputDTO(CellTextEmbeddingsDTO):
    """Input payload for pgvector writer."""


class PgVectorIndexWriterModule(BaseModule):
    """Directly persists vectors and metadata into PostgreSQL pgvector ERD tables."""

    definition = ModuleDefinition(
        type="pgvector_index_writer",
        label="PostgreSQL pgvector Writer",
        category="Storage / DB",
        description="셀 임베딩과 청크 메타데이터를 PostgreSQL 16 pgvector DB의 6개 ERD 테이블 및 HNSW 인덱스에 영구 적재합니다.",
        inputs=["input"],
        outputs=["index_output"],
        config_fields=[],
        raw_output=True,
        cacheable=False,
        version="1",
        task=ModuleTaskPolicy(
            retries=2,
            retry_delay_seconds=3,
            timeout_seconds=3600,
            tags=["postgres", "storage"],
            resource_profile="high-memory",
        ),
    )
    input_model = PgVectorIndexWriterInputDTO
    config_model = EmptyModuleConfigDTO
    output_model = VectorIndexDTO

    def __init__(
        self,
        artifact_store: EmbeddingArtifactStore,
        db_manager: DatabaseManager,
        pgvector_store: PgVectorStore,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
    ) -> None:
        self.artifact_store = artifact_store
        self.db_manager = db_manager
        self.pgvector_store = pgvector_store
        self.embedding_encoder = embedding_encoder
        self.processed_dir = processed_dir.resolve()

    def execute(
        self,
        input_data: PgVectorIndexWriterInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Persist cell embeddings and workbook metadata in a PostgreSQL pgvector index.
        
        Parameters:
            payload (BaseModel): Input containing the embedding artifact, workbook metadata,
                embedding configuration, and source items.
        
        Returns:
            Dict[str, Any]: Metadata for the created index, including its identifier,
                workbook, model, embedding dimension, and document count.
        """
        vectors = self.artifact_store.vector_sequence(
            input_data.artifact_id,
            len(input_data.items),
            input_data.dimension,
        )

        collection_name = PgVectorStore.index_id(input_data.artifact_id)
        self.report_progress(
            {
                "phase": "storage_batches",
                "target_index_id": collection_name,
                "completed_batches": 0,
                "total_batches": max(
                    1,
                    (len(input_data.items) + PGVECTOR_INSERT_BATCH_SIZE - 1)
                    // PGVECTOR_INSERT_BATCH_SIZE,
                ),
                "completed_items": 0,
                "total_items": len(input_data.items),
            }
        )

        # 1. Save source file metadata to PostgreSQL
        self.db_manager.save_source_file(
            file_id=input_data.workbook_hash,
            file_name=input_data.file_name,
            file_hash=input_data.workbook_hash,
            file_size=0,
            file_type="excel",
            storage_path=str(
                (self.processed_dir / Path(input_data.file_name).name).resolve()
            ),
        )

        # 2. Save embeddings in bounded file/DB batches. The full vector matrix is
        # never materialized in memory.
        documents = lazy_cell_documents(
            items=input_data.items,
            file_name=input_data.file_name,
            workbook_hash=input_data.workbook_hash,
            index_id=collection_name,
        )
        self.pgvector_store.put_documents(
            index_id=collection_name,
            documents=documents,
            model_name=input_data.model,
            vectors=vectors,
            metadata={
                "file_name": input_data.file_name,
                "workbook_hash": input_data.workbook_hash,
                "model": input_data.model,
                "dimension": input_data.dimension,
                "document_count": len(input_data.items),
                "duration_seconds": input_data.duration_seconds,
                "total_tokens": input_data.total_tokens,
                "estimated_cost_usd": input_data.estimated_cost_usd,
                "estimated_cost_krw": input_data.estimated_cost_krw,
                "batch_size": input_data.batch_size,
            },
            embedding_encoder=self.embedding_encoder,
            progress_callback=lambda progress: self.report_progress(
                {
                    "phase": "storage_batches",
                    "target_index_id": collection_name,
                    **progress,
                }
            ),
        )

        return {
            "index_id": collection_name,
            "file_name": input_data.file_name,
            "workbook_hash": input_data.workbook_hash,
            "model": input_data.model,
            "dimension": input_data.dimension,
            "document_count": len(input_data.items),
        }
