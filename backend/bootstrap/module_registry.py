from pathlib import Path
from typing import Callable, Iterable

from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from backend.platform.openai.responses import OpenAIResponsesClient
from backend.platform.pgvector import PgVectorRepositorySet
from backend.shared.application.embeddings import EmbeddingEncoder
from backend.storage.data_sources.shard_coordinator import IngestionShardCoordinator
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
from modules.registry import BaseModuleRegistry
from modules.retrieval.context_expander import PgContextExpanderModule
from modules.retrieval.pgvector_retriever import PgVectorRetrieverModule
from modules.retrieval.postgres_native_keyword_retriever import (
    PostgresNativeKeywordRetrieverModule,
)
from modules.retrieval.rrf_fusion import RrfFusionModule
from modules.storage.company_entity_extractor import CompanyEntityExtractorModule
from modules.storage.pgvector_data_scope import PgVectorDataScopeModule
from modules.storage.pgvector_index_writer import PgVectorIndexWriterModule
from modules.storage.processed_file_selector import ProcessedFileSelectorModule
from modules.storage.qa_example_loader import QaExampleLoaderModule
from modules.storage.sheet_metadata_persistence import SheetMetadataPersistenceModule
from modules.structure.cell_text_serializer import CellTextSerializerModule
from modules.structure.luna_vlm_structure_detector import LunaVlmStructureDetectorModule


class ModuleRegistry(BaseModuleRegistry):
    """Owns module discovery and independent execution by module type."""

    def __init__(
        self,
        *,
        completion_client: OpenAIResponsesClient,
        embedding_encoder: EmbeddingEncoder,
        embedding_artifact_store: EmbeddingArtifactStore,
        ingestion_shard_coordinator: IngestionShardCoordinator | None = None,
        pgvector_store: PgVectorStore,
        db_manager: DatabaseManager,
        processed_dir: Path = PROCESSED_DATA_DIR,
        spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        self.pgvector_store = pgvector_store
        self.pgvector_repositories = PgVectorRepositorySet.create(pgvector_store)
        self.db_manager = db_manager
        super().__init__(embedding_artifact_store)
        workbook_catalog = WorkbookCatalog(processed_dir)
        sheet_renderer = ExcelSheetRenderer()
        self._register_domain_factories(
            (
                self._factory(QueryInputModule),
                self._factory(
                    DecomposerModule,
                    completion_client=completion_client,
                ),
                self._factory(
                    LlmQueryRouterModule,
                    completion_client=completion_client,
                ),
                self._factory(
                    SemanticQueryMatcherModule,
                    encoder=embedding_encoder,
                    artifact_store=embedding_artifact_store,
                ),
                self._factory(EmbedderModule, encoder=embedding_encoder),
            )
        )
        self._register_domain_factories(
            (
                self._factory(
                    PgVectorDataScopeModule,
                    pgvector_store=self.pgvector_repositories.retrieval,
                ),
                self._factory(
                    PgVectorRetrieverModule,
                    self.pgvector_repositories.retrieval,
                ),
                self._factory(
                    PostgresNativeKeywordRetrieverModule,
                    self.pgvector_repositories.retrieval,
                ),
                self._factory(RrfFusionModule),
                self._factory(
                    PgContextExpanderModule,
                    self.pgvector_repositories.retrieval,
                ),
            )
        )
        self._register_domain_factories(
            (
                self._factory(
                    CellTextEmbedderModule,
                    encoder=embedding_encoder,
                    artifact_store=embedding_artifact_store,
                    shard_coordinator=ingestion_shard_coordinator,
                ),
                self._factory(
                    PgVectorIndexWriterModule,
                    artifact_store=embedding_artifact_store,
                    db_manager=self.db_manager,
                    pgvector_store=self.pgvector_repositories.ingestion,
                    embedding_encoder=embedding_encoder,
                    processed_dir=processed_dir,
                    shard_coordinator=ingestion_shard_coordinator,
                ),
                self._factory(
                    ProcessedFileSelectorModule,
                    catalog=workbook_catalog,
                ),
                self._factory(
                    LunaVlmStructureDetectorModule,
                    vision_client=completion_client,
                    catalog=workbook_catalog,
                    renderer=sheet_renderer,
                    artifact_dir=spreadsheet_artifact_dir,
                ),
                self._factory(CellTextSerializerModule, catalog=workbook_catalog),
                self._factory(
                    CompanyEntityExtractorModule,
                    completion_client=completion_client,
                    pgvector_store=self.pgvector_repositories.catalog,
                    catalog=workbook_catalog,
                ),
                self._factory(
                    SheetMetadataPersistenceModule,
                    db_manager=self.db_manager,
                    catalog=workbook_catalog,
                ),
                self._factory(QaExampleLoaderModule),
            )
        )
        self._register_domain_factories(
            (
                self._factory(
                    ReaderModule,
                    completion_client,
                    self.pgvector_repositories.retrieval,
                ),
            )
        )

    @staticmethod
    def _factory(
        module_class: type[BaseModule],
        *args: object,
        **kwargs: object,
    ) -> tuple[str, Callable[[], BaseModule]]:
        module_type = module_class.definition.type

        def create() -> BaseModule:
            return module_class(*args, **kwargs)

        return module_type, create

    def _register_domain_factories(
        self,
        factories: Iterable[tuple[str, Callable[[], BaseModule]]],
    ) -> None:
        for module_type, factory in factories:
            self.register_factory(module_type, factory)
