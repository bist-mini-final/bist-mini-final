from pathlib import Path
from typing import Dict, List, Optional

from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from backend.providers.embeddings.factory import EmbeddingEncoder
from backend.providers.llm.chat_completion import ChatCompletionClient
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import BaseModule
from modules.embedding.cell_text_embedder import CellTextEmbedderModule
from modules.embedding.query_embedder import EmbedderModule
from modules.query.decomposer import DecomposerModule
from modules.query.llm_query_router import LlmQueryRouterModule
from modules.query.query_input import QueryInputModule
from modules.query.semantic_query_matcher import SemanticQueryMatcherModule
from modules.reader.reader import ReaderModule
from modules.retrieval.context_expander import PgContextExpanderModule
from modules.retrieval.pgvector_retriever import PgVectorRetrieverModule
from modules.retrieval.postgres_native_keyword_retriever import (
    PostgresNativeKeywordRetrieverModule,
)
from modules.retrieval.rrf_fusion import RrfFusionModule
from modules.storage.company_entity_extractor import CompanyEntityExtractorModule
from modules.storage.pgvector_collection_loader import PgVectorCollectionLoaderModule
from modules.storage.pgvector_index_writer import PgVectorIndexWriterModule
from modules.storage.processed_file_selector import ProcessedFileSelectorModule
from modules.storage.qa_example_loader import QaExampleLoaderModule
from modules.storage.sheet_metadata_persistence import SheetMetadataPersistenceModule
from modules.structure.cell_text_serializer import CellTextSerializerModule
from modules.structure.luna_vlm_structure_detector import LunaVlmStructureDetectorModule

from .registry_base import BaseModuleRegistry


class ModuleRegistry(BaseModuleRegistry):
    """Owns module discovery and independent execution by module type."""

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
        pgvector_store: Optional[PgVectorStore] = None,
        db_manager: Optional[DatabaseManager] = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
        spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        shared_completion_client = completion_client or ChatCompletionClient()
        embedding_artifacts = (
            embedding_artifact_store or EmbeddingArtifactStore()
        )
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()
        isolated_worker_spec: Optional[Dict[str, str]] = None
        if completion_client is None and embedding_encoder is None:
            isolated_worker_spec = {
                "embedding_artifact_dir": str(embedding_artifacts.directory),
                "processed_dir": str(processed_dir),
                "spreadsheet_artifact_dir": str(spreadsheet_artifact_dir),
            }
        super().__init__(
            embedding_artifacts,
            isolated_worker_spec=isolated_worker_spec,
        )
        modules: List[BaseModule] = [
            QueryInputModule(),
            DecomposerModule(completion_client=shared_completion_client),
            LlmQueryRouterModule(completion_client=shared_completion_client),
            SemanticQueryMatcherModule(encoder=embedding_encoder),
            EmbedderModule(encoder=embedding_encoder),
            CellTextEmbedderModule(
                encoder=embedding_encoder,
                artifact_store=embedding_artifacts,
            ),
            PgVectorIndexWriterModule(
                artifact_store=embedding_artifacts,
                db_manager=self.db_manager,
                pgvector_store=self.pgvector_store,
                embedding_encoder=embedding_encoder,
                processed_dir=processed_dir,
            ),
            PgVectorCollectionLoaderModule(
                pgvector_store=self.pgvector_store,
                db_manager=self.db_manager,
            ),
            PgVectorRetrieverModule(self.pgvector_store),
            PostgresNativeKeywordRetrieverModule(self.pgvector_store),
            RrfFusionModule(),
            PgContextExpanderModule(self.pgvector_store),
            ReaderModule(shared_completion_client, self.pgvector_store),
            ProcessedFileSelectorModule(processed_dir=processed_dir),
            LunaVlmStructureDetectorModule(
                processed_dir=processed_dir,
                artifact_dir=spreadsheet_artifact_dir,
            ),
            CellTextSerializerModule(processed_dir=processed_dir),
            CompanyEntityExtractorModule(
                processed_dir=processed_dir,
                completion_client=shared_completion_client,
                pgvector_store=self.pgvector_store,
            ),
            SheetMetadataPersistenceModule(
                db_manager=self.db_manager,
            ),
            QaExampleLoaderModule(),
        ]
        self.register(modules)
