from pathlib import Path
from typing import Dict, List, Optional

from ..core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from ..embeddings.factory import EmbeddingEncoder
from ..llm.chat_completion import ChatCompletionClient
from ..modules.answer_refiner import AnswerRefinerModule
from ..modules.answer_cache_writer import AnswerCacheWriterModule
from ..modules.base import ExecutableModule
from ..modules.bfs_llm_structure_detector import BfsLlmStructureDetectorModule
from ..modules.bm25_retriever import Bm25RetrieverModule
from ..modules.cell_text_embedder import CellTextEmbedderModule
from ..modules.cell_text_serializer import CellTextSerializerModule
from ..modules.company_entity_extractor import CompanyEntityExtractorModule
from ..modules.context_expander import ContextExpanderModule
from ..modules.dataframe_source import DataframeSourceModule
from ..modules.decomposer import DecomposerModule
from ..modules.dense_retriever import DenseRetrieverModule
from ..modules.docling_table_detector import DoclingTableDetectorModule
from ..modules.embedder import EmbedderModule
from ..modules.exhaustive_cell_text_serializer import (
    ExhaustiveCellTextSerializerModule,
)
from ..modules.image_tile_source import ImageTileSourceModule
from ..modules.index_company_persistence import IndexCompanyPersistenceModule
from ..modules.json_inspector import JsonInspectorModule
from ..modules.json_transformer import JsonTransformerModule
from ..modules.local_vlm_structure_detector import LocalVlmStructureDetectorModule
from ..modules.luna_vlm_structure_detector import LunaVlmStructureDetectorModule
from ..modules.openpyxl_region_detector import OpenpyxlRegionDetectorModule
from ..modules.pgvector_collection_loader import PgVectorCollectionLoaderModule
from ..modules.pgvector_index_writer import PgVectorIndexWriterModule
from ..modules.pgvector_retriever import PgVectorRetrieverModule
from ..modules.prebuilt_index_loader import PrebuiltIndexLoaderModule
from ..modules.processed_file_selector import ProcessedFileSelectorModule
from ..modules.qa_example_loader import QaExampleLoaderModule
from ..modules.query_input import QueryInputModule
from ..modules.reader import ReaderModule
from ..modules.rrf_fusion import RrfFusionModule
from ..modules.sheet_metadata_persistence import SheetMetadataPersistenceModule
from ..modules.vector_index_writer import VectorIndexWriterModule
from ..storage.answer_cache import AnswerCacheRepository
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore
from .registry_base import BaseModuleRegistry


class ModuleRegistry(BaseModuleRegistry):
    """Owns module discovery and independent execution by module type."""

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
        """
        Initialize the registry and register all supported executable modules.
        
        Parameters:
            repository (AnswerCacheRepository): Repository used to cache answers.
            processed_dir (Path): Directory containing processed data artifacts.
            spreadsheet_artifact_dir (Path): Directory for spreadsheet processing artifacts.
        
        Raises:
            ValueError: If multiple modules declare the same type.
        """
        embedding_artifacts = (
            embedding_artifact_store or EmbeddingArtifactStore()
        )
        vector_indexes = vector_index_store or VectorIndexStore()
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
                "vector_index_dir": str(vector_indexes.directory),
                "processed_dir": str(processed_dir),
                "spreadsheet_artifact_dir": str(spreadsheet_artifact_dir),
            }
        super().__init__(
            repository,
            embedding_artifacts,
            vector_indexes,
            isolated_worker_spec=isolated_worker_spec,
        )
        modules: List[ExecutableModule] = [
            QueryInputModule(repository=self.repository),
            DecomposerModule(completion_client=completion_client),
            EmbedderModule(encoder=embedding_encoder),
            CellTextEmbedderModule(
                encoder=embedding_encoder,
                artifact_store=embedding_artifacts,
            ),
            VectorIndexWriterModule(
                artifact_store=embedding_artifacts,
                index_store=vector_indexes,
            ),
            PgVectorIndexWriterModule(
                artifact_store=embedding_artifacts,
                db_manager=self.db_manager,
                pgvector_store=self.pgvector_store,
                processed_dir=processed_dir,
            ),
            PrebuiltIndexLoaderModule(
                vector_index_store=vector_indexes,
            ),
            PgVectorCollectionLoaderModule(
                pgvector_store=self.pgvector_store,
                db_manager=self.db_manager,
            ),
            Bm25RetrieverModule(),
            DenseRetrieverModule(vector_indexes),
            PgVectorRetrieverModule(self.pgvector_store),
            RrfFusionModule(),
            ContextExpanderModule(),
            ReaderModule(completion_client),
            AnswerRefinerModule(
                completion_client=completion_client,
                pgvector_store=self.pgvector_store,
            ),
            AnswerCacheWriterModule(repository),
            JsonTransformerModule(),
            JsonInspectorModule(),
            ProcessedFileSelectorModule(processed_dir=processed_dir),
            BfsLlmStructureDetectorModule(
                completion_client=completion_client,
                processed_dir=processed_dir,
                artifact_dir=spreadsheet_artifact_dir,
            ),
            LocalVlmStructureDetectorModule(
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
                processed_dir=processed_dir,
            ),
            IndexCompanyPersistenceModule(pgvector_store=self.pgvector_store),
            DataframeSourceModule(),
            ImageTileSourceModule(),
            QaExampleLoaderModule(),
        ]
        self.register(modules)
