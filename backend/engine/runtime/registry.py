from pathlib import Path
from typing import List

from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.providers.openai_responses import OpenAIResponsesClient
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.spreadsheets.sheet_renderer import ExcelSheetRenderer
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog
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
        *,
        completion_client: OpenAIResponsesClient,
        embedding_encoder: EmbeddingEncoder,
        embedding_artifact_store: EmbeddingArtifactStore,
        pgvector_store: PgVectorStore,
        db_manager: DatabaseManager,
        processed_dir: Path = PROCESSED_DATA_DIR,
        spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        self.pgvector_store = pgvector_store
        self.db_manager = db_manager
        super().__init__(embedding_artifact_store)
        workbook_catalog = WorkbookCatalog(processed_dir)
        sheet_renderer = ExcelSheetRenderer()
        modules: List[BaseModule] = [
            QueryInputModule(),
            DecomposerModule(completion_client=completion_client),
            LlmQueryRouterModule(completion_client=completion_client),
            SemanticQueryMatcherModule(
                encoder=embedding_encoder,
                artifact_store=embedding_artifact_store,
            ),
            EmbedderModule(encoder=embedding_encoder),
            CellTextEmbedderModule(
                encoder=embedding_encoder,
                artifact_store=embedding_artifact_store,
            ),
            PgVectorIndexWriterModule(
                artifact_store=embedding_artifact_store,
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
            ReaderModule(completion_client, self.pgvector_store),
            ProcessedFileSelectorModule(catalog=workbook_catalog),
            LunaVlmStructureDetectorModule(
                vision_client=completion_client,
                catalog=workbook_catalog,
                renderer=sheet_renderer,
                artifact_dir=spreadsheet_artifact_dir,
            ),
            CellTextSerializerModule(catalog=workbook_catalog),
            CompanyEntityExtractorModule(
                completion_client=completion_client,
                pgvector_store=self.pgvector_store,
                catalog=workbook_catalog,
            ),
            SheetMetadataPersistenceModule(
                db_manager=self.db_manager,
                catalog=workbook_catalog,
            ),
            QaExampleLoaderModule(),
        ]
        self.register(modules)
