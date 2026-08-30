from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from backend.engine.runtime.registry_base import BaseModuleRegistry
from modules.common.base_module import BaseModule, ModuleDefinition


class LazyInput(BaseModel):
    value: str


class LazyConfig(BaseModel):
    pass


class LazyOutput(BaseModel):
    value: str


class LazyModule(BaseModule[LazyInput, LazyOutput, LazyConfig]):
    definition = ModuleDefinition(
        type="test.lazy",
        label="Lazy",
        category="test",
        description="lazy registry test module",
        inputs=["value"],
        outputs=["value"],
    )
    input_model = LazyInput
    config_model = LazyConfig
    output_model = LazyOutput

    def execute(
        self,
        input_data: LazyInput,
        config: LazyConfig | None = None,
    ) -> dict[str, Any]:
        return {"value": input_data.value}


def test_factory_constructs_singleton_only_on_first_get(tmp_path) -> None:
    from backend.storage.embedding_artifacts import EmbeddingArtifactStore

    registry = BaseModuleRegistry(EmbeddingArtifactStore(tmp_path))
    created: list[LazyModule] = []

    def factory() -> BaseModule:
        module = LazyModule()
        created.append(module)
        return module

    registry.register_factory("test.lazy", factory)

    assert registry.registered_module_types() == ("test.lazy",)
    assert registry.has("test.lazy")
    assert created == []
    first = registry.get("test.lazy")
    second = registry.get("test.lazy")
    assert first is second
    assert created == [first]


def test_factory_rejects_contract_mismatch(tmp_path) -> None:
    from backend.storage.embedding_artifacts import EmbeddingArtifactStore

    registry = BaseModuleRegistry(EmbeddingArtifactStore(tmp_path))
    registry.register_factory("wrong.type", LazyModule)

    with pytest.raises(ValueError, match="factory 계약 불일치"):
        registry.get("wrong.type")


def test_async_registry_boundary_executes_sync_module(tmp_path) -> None:
    from backend.storage.embedding_artifacts import EmbeddingArtifactStore

    registry = BaseModuleRegistry(EmbeddingArtifactStore(tmp_path))
    registry.register_factory("test.lazy", LazyModule)

    result = asyncio.run(
        registry.execute_async("test.lazy", {"value": "async-safe"})
    )

    assert result == {"value": "async-safe"}
