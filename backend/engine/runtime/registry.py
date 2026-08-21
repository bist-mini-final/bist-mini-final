from pathlib import Path
from typing import Dict, List, Optional

from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from backend.providers.embeddings.factory import EmbeddingEncoder
from backend.providers.llm.chat_completion import ChatCompletionClient
from modules.common.base_module import BaseModule
from modules.embedding.embedder import (
    BatchQueryEmbedderModule,
    CellTextEmbedderModule,
    EmbedderModule,
)
from modules.query.decomposer import (
    AdaptiveQueryDecomposerModule,
    DecomposerModule,
    DirectQueryDecomposerModule,
    TemplateQueryDecomposerModule,
    ThesaurusDecomposerModule,
)
from modules.query.query_input import QueryInputModule
from modules.query.semantic_query_matcher import (
    LlmQueryRouterModule,
    SemanticQueryMatcherModule,
)
from modules.reader.answer_refiner import AnswerRefinerModule
from modules.reader.financial_formula_calculator import FinancialFormulaCalculatorModule
from modules.reader.reader import ReaderModule
from modules.retrieval.context_expander import (
    ContextExpanderModule,
    PgContextExpanderModule,
    TimeseriesContextExpanderModule,
)
from modules.retrieval.pgvector_retriever import (
    PgVectorRetrieverModule,
    SemanticScopedPgVectorRetrieverModule,
)
from modules.retrieval.postgres_native_keyword_retriever import (
    PostgresNativeKeywordRetrieverModule,
)
from modules.retrieval.rrf_fusion import (
    AdaptiveRrfFusionModule,
    RrfFusionModule,
)
from modules.storage.company_entity_extractor import CompanyEntityExtractorModule
from modules.storage.dataframe_source import DataframeSourceModule
from modules.storage.image_tile_source import ImageTileSourceModule
from modules.storage.pgvector_collection_loader import (
    MultiCompanyCollectionLoaderModule,
    PgVectorCollectionLoaderModule,
)
from modules.storage.pgvector_index_writer import PgVectorIndexWriterModule
from modules.storage.processed_file_selector import ProcessedFileSelectorModule
from modules.storage.qa_example_loader import QaExampleLoaderModule
from modules.storage.sheet_metadata_persistence import (
    IndexCompanyPersistenceModule,
    SheetMetadataPersistenceModule,
)
from modules.structure.bfs_llm_structure_detector import BfsLlmStructureDetectorModule
from modules.structure.cell_text_serializer import (
    CellTextSerializerModule,
    ExhaustiveCellTextSerializerModule,
)
from modules.structure.docling_table_detector import DoclingTableDetectorModule
from modules.structure.luna_vlm_structure_detector import LunaVlmStructureDetectorModule
from modules.structure.openpyxl_region_detector import OpenpyxlRegionDetectorModule
from backend.storage.answer_cache import AnswerCacheRepository
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PgVectorStore
from .registry_base import BaseModuleRegistry


class ModuleRegistry(BaseModuleRegistry):
    """Owns module discovery and independent execution by module type."""

    def __init__(
        self,
        repository: AnswerCacheRepository,
        completion_client: Optional[ChatCompletionClient] = None,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
        pgvector_store: Optional[PgVectorStore] = None,
        db_manager: Optional[DatabaseManager] = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
        spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        embedding_artifacts = (
            embedding_artifact_store or EmbeddingArtifactStore()
        )
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()
        isolated_worker_spec: Optional[Dict[str, str]] = None
        if (
            completion_client is None
            and embedding_encoder is None
            and repository.path is not None
        ):
            isolated_worker_spec = {
                "answer_cache_path": str(repository.path),
                "embedding_artifact_dir": str(embedding_artifacts.directory),
                "processed_dir": str(processed_dir),
                "spreadsheet_artifact_dir": str(spreadsheet_artifact_dir),
            }
        super().__init__(
            repository,
            embedding_artifacts,
            isolated_worker_spec=isolated_worker_spec,
        )
        modules: List[BaseModule] = [
            QueryInputModule(repository=self.repository),
            DecomposerModule(completion_client=completion_client),
            AdaptiveQueryDecomposerModule(completion_client=completion_client),
            DirectQueryDecomposerModule(),
            TemplateQueryDecomposerModule(completion_client=completion_client),
            LlmQueryRouterModule(completion_client=completion_client),
            SemanticQueryMatcherModule(encoder=embedding_encoder),
            ThesaurusDecomposerModule(completion_client=completion_client),
            EmbedderModule(encoder=embedding_encoder),
            CellTextEmbedderModule(
                encoder=embedding_encoder,
                artifact_store=embedding_artifacts,
            ),
            PgVectorIndexWriterModule(
                artifact_store=embedding_artifacts,
                db_manager=self.db_manager,
                pgvector_store=self.pgvector_store,
                processed_dir=processed_dir,
            ),
            PgVectorCollectionLoaderModule(
                pgvector_store=self.pgvector_store,
                db_manager=self.db_manager,
            ),
            MultiCompanyCollectionLoaderModule(
                pgvector_store=self.pgvector_store,
                db_manager=self.db_manager,
            ),
            PgVectorRetrieverModule(self.pgvector_store),
            SemanticScopedPgVectorRetrieverModule(self.pgvector_store),
            PostgresNativeKeywordRetrieverModule(self.pgvector_store),
            BatchQueryEmbedderModule(encoder=embedding_encoder),
            RrfFusionModule(),
            AdaptiveRrfFusionModule(),
            ContextExpanderModule(),
            TimeseriesContextExpanderModule(),
            PgContextExpanderModule(self.pgvector_store),
            FinancialFormulaCalculatorModule(completion_client=completion_client),
            ReaderModule(completion_client),
            AnswerRefinerModule(
                completion_client=completion_client,
                pgvector_store=self.pgvector_store,
            ),
            ProcessedFileSelectorModule(processed_dir=processed_dir),
            BfsLlmStructureDetectorModule(
                completion_client=completion_client,
                processed_dir=processed_dir,
                artifact_dir=spreadsheet_artifact_dir,
            ),
            LunaVlmStructureDetectorModule(
                processed_dir=processed_dir,
                artifact_dir=spreadsheet_artifact_dir,
            ),
            DoclingTableDetectorModule(
                processed_dir=processed_dir,
                artifact_dir=spreadsheet_artifact_dir,
            ),
            OpenpyxlRegionDetectorModule(processed_dir=processed_dir),
            CellTextSerializerModule(processed_dir=processed_dir),
            ExhaustiveCellTextSerializerModule(processed_dir=processed_dir),
            CompanyEntityExtractorModule(
                processed_dir=processed_dir,
                completion_client=completion_client,
            ),
            SheetMetadataPersistenceModule(
                db_manager=self.db_manager,
            ),
            IndexCompanyPersistenceModule(
                pgvector_store=self.pgvector_store,
            ),
            DataframeSourceModule(processed_dir=processed_dir),
            ImageTileSourceModule(processed_dir=processed_dir),
            QaExampleLoaderModule(),
        ]
        self.register(modules)
