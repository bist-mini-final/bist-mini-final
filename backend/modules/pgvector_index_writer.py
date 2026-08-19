from pathlib import Path
from typing import Any, Dict, Optional, cast

from pydantic import BaseModel, Field

from ..embeddings.factory import EmbeddingEncoder
from ..core.settings import PROCESSED_DATA_DIR
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PGVECTOR_INSERT_BATCH_SIZE, PgVectorStore
from ..storage.vector_index import VectorIndexStore
from .base import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
)
from .cell_text_embedder import CellTextEmbeddingsDTO
from .vector_index_writer import VectorIndexDTO


class PgVectorIndexWriterInputDTO(CellTextEmbeddingsDTO):
    """Input payload for pgvector writer."""


class PgVectorIndexWriterModule(ExecutableModule):
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

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        """
        Persist cell embeddings and workbook metadata in a PostgreSQL pgvector index.
        
        Parameters:
            payload (BaseModel): Input containing the embedding artifact, workbook metadata,
                embedding configuration, and source items.
        
        Returns:
            Dict[str, Any]: Metadata for the created index, including its identifier,
                workbook, model, embedding dimension, and document count.
        """
        input_data = cast(PgVectorIndexWriterInputDTO, payload)
        vectors = self.artifact_store.get(
            input_data.artifact_id,
            len(input_data.items),
            input_data.dimension,
        )

        collection_name = VectorIndexStore.index_id(input_data.artifact_id)
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
