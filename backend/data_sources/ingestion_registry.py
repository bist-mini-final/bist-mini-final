"""Lean module registry used by the one-shot Excel ingestion worker."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from ..embeddings.factory import EmbeddingEncoder
from ..llm.chat_completion import ChatCompletionClient
from ..modules.cell_text_embedder import CellTextEmbedderModule
from ..modules.cell_text_serializer import CellTextSerializerModule
from ..modules.company_entity_extractor import CompanyEntityExtractorModule
from ..modules.exhaustive_cell_text_serializer import (
    ExhaustiveCellTextSerializerModule,
)
from ..modules.index_company_persistence import IndexCompanyPersistenceModule
from ..modules.luna_vlm_structure_detector import LunaVlmStructureDetectorModule
from ..modules.pgvector_index_writer import PgVectorIndexWriterModule
from ..modules.processed_file_selector import ProcessedFileSelectorModule
from ..modules.sheet_metadata_persistence import SheetMetadataPersistenceModule
from ..runtime.registry_base import BaseModuleRegistry
from ..storage.answer_cache import AnswerCacheRepository
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore


class IngestionModuleRegistry(BaseModuleRegistry):
    """Register only modules reachable from supported ingestion workflows."""

    def __init__(
        self,
        repository: AnswerCacheRepository,
        completion_client: Optional[ChatCompletionClient] = None,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
        vector_index_store: Optional[VectorIndexStore] = None,
        pgvector_store: Optional[PgVectorStore] = None,
        db_manager: Optional[DatabaseManager] = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
        spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        artifacts = embedding_artifact_store or EmbeddingArtifactStore()
        indexes = vector_index_store or VectorIndexStore()
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()
        # A one-shot job is already the failure/cancellation boundary. Avoid a
        # second spawned Python process for every node.
        super().__init__(repository, artifacts, indexes, isolated_worker_spec=None)
        self.register(
            [
                ProcessedFileSelectorModule(processed_dir=processed_dir),
                LunaVlmStructureDetectorModule(
                    processed_dir=processed_dir,
                    artifact_dir=spreadsheet_artifact_dir,
                ),
                CellTextSerializerModule(processed_dir=processed_dir),
                ExhaustiveCellTextSerializerModule(processed_dir=processed_dir),
                CellTextEmbedderModule(
                    encoder=embedding_encoder,
                    artifact_store=artifacts,
                ),
                PgVectorIndexWriterModule(
                    artifact_store=artifacts,
                    db_manager=self.db_manager,
                    pgvector_store=self.pgvector_store,
                    processed_dir=processed_dir,
                ),
                CompanyEntityExtractorModule(
                    processed_dir=processed_dir,
                    completion_client=completion_client,
                ),
                SheetMetadataPersistenceModule(
                    db_manager=self.db_manager,
                    processed_dir=processed_dir,
                ),
                IndexCompanyPersistenceModule(
                    pgvector_store=self.pgvector_store,
                ),
            ]
        )
