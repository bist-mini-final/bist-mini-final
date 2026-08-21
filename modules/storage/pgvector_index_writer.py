from __future__ import annotations

from pathlib import Path
from typing import Optional, Any, Dict, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.embeddings.factory import EmbeddingEncoder
from backend.core.settings import PROCESSED_DATA_DIR
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PGVECTOR_INSERT_BATCH_SIZE, PgVectorStore
from modules.common.base_module import (
    EmptyModuleConfigDTO,
    BaseModule,
    ModuleDefinition,
    ModuleDTO,
    ModuleTaskPolicy,
)
from modules.embedding.embedder import CellTextEmbeddingsDTO


class VectorIndexDTO(ModuleDTO):
    index_id: str = Field(
        pattern=r"^[a-f0-9]{64}$",
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
        category="Transform",
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
    execution_model = PgVectorIndexWriterInputDTO
    output_model = VectorIndexDTO

    def __init__(
        self,
        artifact_store: Optional[EmbeddingArtifactStore] = None,
        db_manager: Optional[DatabaseManager] = None,
        pgvector_store: Optional[PgVectorStore] = None,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
    ) -> None:
        self.artifact_store = artifact_store or EmbeddingArtifactStore()
        self.db_manager = db_manager or DatabaseManager()
        self.pgvector_store = pgvector_store or PgVectorStore()
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
        if config is None and isinstance(input_data, PgVectorIndexWriterInputDTO):
            cfg = input_data
        else:
            cfg = config or EmptyModuleConfigDTO()
        vectors = self.artifact_store.get(
            input_data.artifact_id,
            len(input_data.items),
            input_data.dimension,
        )

        collection_name = PgVectorStore.index_id(input_data.artifact_id)
        items_dict = [item.model_dump(mode="json") for item in input_data.items]
        self.report_progress(
            {
                "phase": "storage_batches",
                "target_index_id": collection_name,
                "completed_batches": 0,
                "total_batches": max(
                    1,
                    (len(items_dict) + PGVECTOR_INSERT_BATCH_SIZE - 1)
                    // PGVECTOR_INSERT_BATCH_SIZE,
                ),
                "completed_items": 0,
                "total_items": len(items_dict),
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

        # 2. Save embeddings into pgvector via PgVectorStore (LangChain collection & embeddings)
        self.pgvector_store.put(
            index_id=collection_name,
            vectors=vectors,
            metadata={
                "file_name": input_data.file_name,
                "workbook_hash": input_data.workbook_hash,
                "model": input_data.model,
                "dimension": input_data.dimension,
                "document_count": len(items_dict),
                "duration_seconds": input_data.duration_seconds,
                "total_tokens": input_data.total_tokens,
                "estimated_cost_usd": input_data.estimated_cost_usd,
                "estimated_cost_krw": input_data.estimated_cost_krw,
                "batch_size": input_data.batch_size,
                "items": items_dict,
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
