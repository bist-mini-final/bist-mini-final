"""Provider-neutral change-hint contract for persisted state streams."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class StateStreamBroker(Protocol):
    """Publish hints only; domain state always remains in persistent storage."""

    async def publish(self, topic: str) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[None]: ...

    async def aclose(self) -> None: ...


__all__ = ["StateStreamBroker"]
