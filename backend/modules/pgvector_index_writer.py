from typing import Any, Dict, Optional, cast

from pydantic import BaseModel, Field

from ..embeddings.factory import EmbeddingEncoder
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
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
    ) -> None:
        self.artifact_store = artifact_store or EmbeddingArtifactStore()
        self.db_manager = db_manager or DatabaseManager()
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.embedding_encoder = embedding_encoder

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(PgVectorIndexWriterInputDTO, payload)
        vectors = self.artifact_store.get(
            input_data.artifact_id,
            len(input_data.items),
            input_data.dimension,
        )

        collection_name = VectorIndexStore.index_id(input_data.artifact_id)
        items_dict = [item.model_dump(mode="json") for item in input_data.items]

        # 1. Save source file metadata to PostgreSQL
        self.db_manager.save_source_file(
            file_id=input_data.workbook_hash,
            file_name=input_data.file_name,
            file_hash=input_data.workbook_hash,
            file_size=0,
            file_type="excel",
            storage_path=f"data/source_files/{input_data.file_name}",
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
                "items": items_dict,
            },
            embedding_encoder=self.embedding_encoder,
        )

        return {
            "index_id": collection_name,
            "file_name": input_data.file_name,
            "workbook_hash": input_data.workbook_hash,
            "model": input_data.model,
            "dimension": input_data.dimension,
            "document_count": len(input_data.items),
        }
