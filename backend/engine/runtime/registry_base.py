"""Shared registry mechanics without importing every application module."""

from __future__ import annotations

from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.base_module import BaseModule

_CONFIG_UNSET = object()


class BaseModuleRegistry:
    """Minimal interface consumed by the workflow executor."""

    def __init__(
        self,
        embedding_artifact_store: Optional[EmbeddingArtifactStore] = None,
        *,
        isolated_worker_spec: Optional[Dict[str, str]] = None,
    ) -> None:
        self.embedding_artifact_store = embedding_artifact_store or EmbeddingArtifactStore()
        self.isolated_worker_spec = isolated_worker_spec
        self._modules: Dict[str, BaseModule] = {}

    def register(self, modules: Iterable[BaseModule]) -> None:
        for module in modules:
            module_type = module.definition.type
            if module_type in self._modules:
                raise ValueError(f"중복 모듈 type입니다: {module_type}")
            self._modules[module_type] = module

    def list_modules(self) -> list[BaseModule]:
        return list(self._modules.values())

    def definitions(self) -> list[Dict[str, Any]]:
        return [module.contract() for module in self._modules.values()]

    def definition(self, module_type: str) -> Dict[str, Any]:
        return self.get(module_type).contract()

    def has(self, module_type: str) -> bool:
        return module_type in self._modules

    def get(self, module_type: str) -> BaseModule:
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
            "embedding_artifacts_removed": self.embedding_artifact_store.clear(),
        }


__all__ = ["BaseModuleRegistry"]
