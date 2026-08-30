"""Pure declarative contracts for product-owned jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple, TypeAlias


@dataclass(frozen=True)
class JobNode:
    node_id: str
    module_type: str
    config: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    values: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class JobEdge:
    edge_id: str
    source: str
    target: str
    source_output: str
    target_input: str
    source_branch: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class BaseJobDefinition:
    """Fields shared by every immutable product job definition."""

    job_id: str
    name: str
    description: str
    queue_name: str
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.job_id or not self.name or not self.queue_name:
            raise ValueError("job_id, name, queue_name은 비어 있을 수 없습니다")


@dataclass(frozen=True, kw_only=True)
class DagJobDefinition(BaseJobDefinition):
    """Canonical module DAG executed by the shared workflow worker."""

    nodes: Tuple[JobNode, ...]
    edges: Tuple[JobEdge, ...] = ()
    template: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.nodes:
            raise ValueError(f"DAG job {self.job_id}에는 노드가 필요합니다")
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError(f"job {self.job_id}에 중복 node_id가 있습니다")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError(f"job {self.job_id}에 중복 edge_id가 있습니다")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(
                    f"job {self.job_id}의 edge {edge.edge_id}가 없는 노드를 참조합니다"
                )


@dataclass(frozen=True)
class KubernetesWorkerPolicy:
    """KEDA/PostgreSQL scaling contract owned by a worker job."""

    deployment_name: str
    pending_query: str
    active_deadline_seconds: int = 21_600
    mount_data_volume: bool = False
    max_replica_count: int | None = None

    def __post_init__(self) -> None:
        if not self.deployment_name or not self.pending_query.strip():
            raise ValueError("Kubernetes worker policy가 완전하지 않습니다")
        if self.active_deadline_seconds < 1:
            raise ValueError("active_deadline_seconds는 1 이상이어야 합니다")
        if self.max_replica_count is not None and self.max_replica_count < 1:
            raise ValueError("max_replica_count는 1 이상이어야 합니다")


@dataclass(frozen=True, kw_only=True)
class WorkerJobDefinition(BaseJobDefinition):
    """Leased queue handler with one explicit Python entrypoint."""

    worker_entrypoint: str
    kubernetes: KubernetesWorkerPolicy

    def __post_init__(self) -> None:
        super().__post_init__()
        module_name, separator, function_name = self.worker_entrypoint.partition(":")
        if not separator or not module_name or not function_name:
            raise ValueError(
                f"worker job {self.job_id} entrypoint는 module:function 형식이어야 합니다"
            )

    @property
    def worker_module(self) -> str:
        return self.worker_entrypoint.partition(":")[0]


JobDefinition: TypeAlias = DagJobDefinition | WorkerJobDefinition

__all__ = [
    "BaseJobDefinition",
    "DagJobDefinition",
    "JobDefinition",
    "JobEdge",
    "JobNode",
    "KubernetesWorkerPolicy",
    "WorkerJobDefinition",
]
