"""Cross-domain application contracts and coordination primitives."""

from .embeddings import EmbeddingEncoder
from .observability import (
    ObservabilityContext,
    bind_observability_context,
    current_observability_context,
    observability_log_extra,
)
from .snapshots import VersionedSnapshotRecord, VersionedSnapshotRepository
from .state_stream import SharedStateStream
from .state_stream_broker import StateStreamBroker
from .workers import LeasedWorker, WorkerLeaseSpec, default_worker_id

__all__ = [
    "EmbeddingEncoder",
    "LeasedWorker",
    "ObservabilityContext",
    "SharedStateStream",
    "StateStreamBroker",
    "VersionedSnapshotRecord",
    "VersionedSnapshotRepository",
    "WorkerLeaseSpec",
    "bind_observability_context",
    "current_observability_context",
    "default_worker_id",
    "observability_log_extra",
]
