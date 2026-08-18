from typing import Any, Dict, List, Optional

from ..embeddings.factory import EmbeddingEncoder
from ..llm.chat_completion import ChatCompletionClient
from ..modules.answer_refiner import AnswerRefinerModule
from ..modules.answer_cache_writer import AnswerCacheWriterModule
from ..modules.base import ExecutableModule
from ..modules.bfs_llm_structure_detector import BfsLlmStructureDetectorModule
from ..modules.bm25_retriever import Bm25RetrieverModule
from ..modules.cell_text_embedder import CellTextEmbedderModule
from ..modules.cell_text_serializer import CellTextSerializerModule
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
from ..modules.vector_index_writer import VectorIndexWriterModule
from ..storage.answer_cache import AnswerCacheRepository
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore


_CONFIG_UNSET = object()


class ModuleRegistry:
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
    ) -> None:
        self.repository = repository
        self.embedding_artifact_store = (
            embedding_artifact_store or EmbeddingArtifactStore()
        )
        self.vector_index_store = vector_index_store or VectorIndexStore()
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()
        self.isolated_worker_spec: Optional[Dict[str, str]] = None
        if (
            completion_client is None
            and embedding_encoder is None
            and repository.path is not None
        ):
            self.isolated_worker_spec = {
                "answer_cache_path": str(repository.path),
                "embedding_artifact_dir": str(self.embedding_artifact_store.directory),
                "vector_index_dir": str(self.vector_index_store.directory),
            }
        modules: List[ExecutableModule] = [
            QueryInputModule(repository=self.repository),
            DecomposerModule(completion_client=completion_client),
            EmbedderModule(encoder=embedding_encoder),
            CellTextEmbedderModule(
                encoder=embedding_encoder,
                artifact_store=self.embedding_artifact_store,
            ),
            VectorIndexWriterModule(
                artifact_store=self.embedding_artifact_store,
                index_store=self.vector_index_store,
            ),
            PgVectorIndexWriterModule(
                artifact_store=self.embedding_artifact_store,
                db_manager=self.db_manager,
                pgvector_store=self.pgvector_store,
            ),
            PrebuiltIndexLoaderModule(
                vector_index_store=self.vector_index_store,
            ),
            PgVectorCollectionLoaderModule(
                pgvector_store=self.pgvector_store,
                db_manager=self.db_manager,
            ),
            Bm25RetrieverModule(),
            DenseRetrieverModule(self.vector_index_store),
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
            ProcessedFileSelectorModule(),
            BfsLlmStructureDetectorModule(completion_client),
            LocalVlmStructureDetectorModule(),
            LunaVlmStructureDetectorModule(),
            DoclingTableDetectorModule(),
            OpenpyxlRegionDetectorModule(),
            CellTextSerializerModule(),
            ExhaustiveCellTextSerializerModule(),
            DataframeSourceModule(),
            ImageTileSourceModule(),
            QaExampleLoaderModule(),
        ]
        self._modules: Dict[str, ExecutableModule] = {}
        for module in modules:
            module_type = module.definition.type
            if module_type in self._modules:
                raise ValueError(f"중복 모듈 type입니다: {module_type}")
            self._modules[module_type] = module

    def definitions(self) -> List[Dict[str, Any]]:
        return [module.contract() for module in self._modules.values()]

    def definition(self, module_type: str) -> Dict[str, Any]:
        return self.get(module_type).contract()

    def get(self, module_type: str) -> ExecutableModule:
        try:
            return self._modules[module_type]
        except KeyError as error:
            raise KeyError(f"지원하지 않는 모듈입니다: {module_type}") from error

    def execute(
        self,
        module_type: str,
        input_payload: Any,
        config: Any = _CONFIG_UNSET,
    ) -> Any:
        """Execute one registered module through the public Input/Config boundary."""

        module = self.get(module_type)
        if config is _CONFIG_UNSET:
            return module.run(input_payload)
        return module.run(input_payload, config)

    def clear_caches(self) -> Dict[str, int]:
        """Clear domain caches owned by registered modules."""

        return {
            "answers_removed": self.repository.clear_cached_answers(),
            "embedding_artifacts_removed": self.embedding_artifact_store.clear(),
            "vector_indexes_removed": self.vector_index_store.clear(),
        }
