"""Module catalog and execution capability required by workflow use cases."""

from __future__ import annotations

from typing import Any, Protocol

from modules.common.base_module import BaseModule


class ModuleRegistryPort(Protocol):
    """Keep workflow orchestration independent from registry construction."""

    def get(self, module_type: str) -> BaseModule: ...

    def execute(
        self,
        module_type: str,
        input_payload: Any,
        config: Any = ...,
    ) -> Any: ...

    async def execute_async(
        self,
        module_type: str,
        input_payload: Any,
        config: Any = ...,
    ) -> Any: ...

    def clear_caches(self) -> dict[str, int]: ...


__all__ = ["ModuleRegistryPort"]
