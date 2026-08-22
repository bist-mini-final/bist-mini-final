"""Declarative base definition for composable workflow jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class JobDefinition:
    """Declarative specification of a composable pipeline job."""

    job_id: str
    name: str
    description: str
    module_sequence: List[str]
    default_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    queue_name: Optional[str] = None


__all__ = ["JobDefinition"]
