"""Storage-neutral contracts for durable, versioned domain snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class VersionedSnapshotRecord:
    """Storage-neutral snapshot envelope.

    Domain payloads stay owned and validated by their feature.  The shared
    repository only manages immutable versions and an atomic current pointer.
    """

    snapshot_id: str
    domain: str
    scope_key: str
    schema_version: int
    source_fingerprint: str
    payload: Mapping[str, Any]
    generated_at: datetime


class VersionedSnapshotRepository(Protocol):
    async def get_current(
        self,
        *,
        domain: str,
        scope_key: str,
    ) -> VersionedSnapshotRecord | None: ...

    async def publish(self, record: VersionedSnapshotRecord) -> None: ...


__all__ = ["VersionedSnapshotRecord", "VersionedSnapshotRepository"]
