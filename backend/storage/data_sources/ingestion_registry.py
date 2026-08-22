"""Lean module registry used by the one-shot Excel ingestion worker."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.providers.embeddings.factory import EmbeddingEncoder
from backend.providers.llm.chat_completion import ChatCompletionClient
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PgVectorStore
from modules.embedding.cell_text_embedder import CellTextEmbedderModule
from modules.storage.company_entity_extractor import CompanyEntityExtractorModule
from modules.storage.pgvector_index_writer import PgVectorIndexWriterModule
from modules.storage.processed_file_selector import ProcessedFileSelectorModule
from modules.storage.sheet_metadata_persistence import (
    SheetMetadataPersistenceModule,
)
from modules.structure.cell_text_serializer import CellTextSerializerModule
from modules.structure.luna_vlm_structure_detector import LunaVlmStructureDetectorModule


class IngestionModuleRegistry(BaseModuleRegistry):
    """Register only modules reachable from supported ingestion workflows."""

    def __init__(
        self,
        completion_client: Optional[Any] = None,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
        pgvector_store: Optional[PgVectorStore] = None,
        db_manager: Optional[DatabaseManager] = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
        spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        artifacts = embedding_artifact_store or EmbeddingArtifactStore()
        shared_completion_client = completion_client or ChatCompletionClient()
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()
        # A one-shot job is already the failure/cancellation boundary. Avoid a
        # second spawned Python process for every node.
        super().__init__(
            artifacts,
            isolated_worker_spec=None,
        )
        self.register(
            [
                ProcessedFileSelectorModule(processed_dir=processed_dir),
                LunaVlmStructureDetectorModule(
                    processed_dir=processed_dir,
                    artifact_dir=spreadsheet_artifact_dir,
                ),
                CellTextSerializerModule(processed_dir=processed_dir),
                CellTextEmbedderModule(
                    encoder=embedding_encoder,
                    artifact_store=artifacts,
                ),
                PgVectorIndexWriterModule(
                    artifact_store=artifacts,
                    db_manager=self.db_manager,
                    pgvector_store=self.pgvector_store,
                    embedding_encoder=embedding_encoder,
                    processed_dir=processed_dir,
                ),
                CompanyEntityExtractorModule(
                    completion_client=shared_completion_client,
                    processed_dir=processed_dir,
                    pgvector_store=self.pgvector_store,
                ),
                SheetMetadataPersistenceModule(
                    db_manager=self.db_manager,
                ),
            ]
        )
