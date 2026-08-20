"""Shared registry mechanics without importing every application module."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..modules.base import ExecutableModule
from ..storage.answer_cache import AnswerCacheRepository
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.vector_index import VectorIndexStore


_CONFIG_UNSET = object()


class BaseModuleRegistry:
    """Minimal interface consumed by the workflow executor."""

    def __init__(
        self,
        repository: AnswerCacheRepository,
        embedding_artifact_store: EmbeddingArtifactStore,
        vector_index_store: VectorIndexStore,
        *,
        isolated_worker_spec: Optional[Dict[str, str]] = None,
    ) -> None:
        self.repository = repository
        self.embedding_artifact_store = embedding_artifact_store
        self.vector_index_store = vector_index_store
        self.isolated_worker_spec = isolated_worker_spec
        self._modules: Dict[str, ExecutableModule] = {}

    def register(self, modules: Iterable[ExecutableModule]) -> None:
        for module in modules:
            module_type = module.definition.type
            if module_type in self._modules:
                raise ValueError(f"중복 모듈 type입니다: {module_type}")
            self._modules[module_type] = module

    def definitions(self) -> list[Dict[str, Any]]:
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
        module = self.get(module_type)
        if config is _CONFIG_UNSET:
            return module.run(input_payload)
        return module.run(input_payload, config)

    def clear_caches(self) -> Dict[str, int]:
        return {
            "answers_removed": self.repository.clear_cached_answers(),
            "embedding_artifacts_removed": self.embedding_artifact_store.clear(),
            "vector_indexes_removed": self.vector_index_store.clear(),
        }
