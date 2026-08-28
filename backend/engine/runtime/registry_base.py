"""Shared registry mechanics without importing every application module."""

from __future__ import annotations

from threading import RLock
from typing import Any, Callable, Dict, Iterable

from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.base_module import BaseModule

_CONFIG_UNSET = object()
ModuleFactory = Callable[[], BaseModule]


class BaseModuleRegistry:
    """Minimal interface consumed by the workflow executor."""

    def __init__(
        self,
        embedding_artifact_store: EmbeddingArtifactStore,
    ) -> None:
        self.embedding_artifact_store = embedding_artifact_store
        self._modules: Dict[str, BaseModule] = {}
        self._factories: Dict[str, ModuleFactory] = {}
        self._factory_lock = RLock()

    def register(self, modules: Iterable[BaseModule]) -> None:
        for module in modules:
            module_type = module.definition.type
            with self._factory_lock:
                if module_type in self._modules or module_type in self._factories:
                    raise ValueError(f"중복 모듈 type입니다: {module_type}")
                self._modules[module_type] = module

    def register_factory(
        self,
        module_type: str,
        factory: ModuleFactory,
    ) -> None:
        """Register one singleton construction recipe without creating it."""
        if not module_type:
            raise ValueError("모듈 type은 비어 있을 수 없습니다")
        with self._factory_lock:
            if module_type in self._modules or module_type in self._factories:
                raise ValueError(f"중복 모듈 type입니다: {module_type}")
            self._factories[module_type] = factory

    def registered_module_types(self) -> tuple[str, ...]:
        """Return stable catalog keys without forcing module construction."""
        with self._factory_lock:
            return tuple((*self._modules, *self._factories))

    def list_modules(self) -> list[BaseModule]:
        return [self.get(module_type) for module_type in self.registered_module_types()]

    def definitions(self) -> list[Dict[str, Any]]:
        return [module.contract() for module in self.list_modules()]

    def definition(self, module_type: str) -> Dict[str, Any]:
        return self.get(module_type).contract()

    def has(self, module_type: str) -> bool:
        with self._factory_lock:
            return module_type in self._modules or module_type in self._factories

    def get(self, module_type: str) -> BaseModule:
        with self._factory_lock:
            module = self._modules.get(module_type)
            if module is not None:
                return module
            factory = self._factories.get(module_type)
            if factory is None:
                raise KeyError(f"지원하지 않는 모듈입니다: {module_type}")
            module = factory()
            actual_type = module.definition.type
            if actual_type != module_type:
                raise ValueError(
                    "모듈 factory 계약 불일치: "
                    f"registered={module_type}, actual={actual_type}"
                )
            self._modules[module_type] = module
            del self._factories[module_type]
            return module

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

    async def execute_async(
        self,
        module_type: str,
        input_payload: Any,
        config: Any = _CONFIG_UNSET,
    ) -> Any:
        """Execute through the non-blocking module adapter boundary."""
        module = self.get(module_type)
        if config is _CONFIG_UNSET:
            return await module.run_async(input_payload)
        return await module.run_async(input_payload, config)

    def clear_caches(self) -> Dict[str, int]:
        return {
            "embedding_artifacts_removed": self.embedding_artifact_store.clear(),
        }


__all__ = ["BaseModuleRegistry", "ModuleFactory"]
