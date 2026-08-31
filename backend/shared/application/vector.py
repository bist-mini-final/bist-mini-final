"""Storage-neutral contracts for atomic vector collection replacement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True, slots=True)
class PgVectorReplacePlan:
    """Retry-stable staging identity shared by COPY workers and finalizers."""

    index_id: str
    operation_id: str
    staging_name: str
    staging_uuid: str
    dimension: int
    metadata: Dict[str, Any]
    published: bool = False


__all__ = ["PgVectorReplacePlan"]
