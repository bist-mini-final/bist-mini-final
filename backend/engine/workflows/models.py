from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
ExecutionBranch = str
OutputBranch = str
NodeStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
RunStatus = Literal["queued", "running", "paused", "completed", "failed"]
BatchStatus = Literal["pending", "running", "completed", "failed"]
OrchestratorBackend = Literal[
    "direct",
    "kubernetes",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CanvasPosition(StrictModel):
    x: float
    y: float


class CanvasViewport(StrictModel):
    x: float = 0
    y: float = 0
    zoom: float = Field(default=1, gt=0, le=4)


class NodeUI(StrictModel):
    width: Optional[float] = Field(default=None, ge=320, le=1200)
    height: Optional[float] = Field(default=None, ge=280, le=1600)
    execution_stopped: bool = False
    column_widths: Dict[str, Annotated[float, Field(ge=80, le=1200)]] = Field(
        default_factory=dict
    )


class WorkflowNode(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    module_type: str = Field(pattern=IDENTIFIER_PATTERN)
    position: CanvasPosition
    config: Dict[str, Any] = Field(default_factory=dict)
    values: Dict[str, Any] = Field(default_factory=dict)
    ui: NodeUI = Field(default_factory=NodeUI)


class WorkflowEdge(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    source: str = Field(pattern=IDENTIFIER_PATTERN)
    target: str = Field(pattern=IDENTIFIER_PATTERN)
    source_output: Optional[str] = None
    target_input: Optional[str] = None
    source_branch: Optional[OutputBranch] = None


class WorkflowGraph(StrictModel):
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)
    viewport: CanvasViewport = Field(default_factory=CanvasViewport)

    @model_validator(mode="before")
    @classmethod
    def migrate_query_lineage_edges(cls, value: Any) -> Any:
        """Upgrade legacy Query→Reader/Cache fan-out to carried query context."""

        if not isinstance(value, Mapping):
            return value
        raw_nodes = value.get("nodes", [])
        if not isinstance(raw_nodes, list):
            return value
        module_by_id = {
            (
                node.get("id")
                if isinstance(node, Mapping)
                else getattr(node, "id", None)
            ): (
                node.get("module_type")
                if isinstance(node, Mapping)
                else getattr(node, "module_type", None)
            )
            for node in raw_nodes
        }
        migrated_edges = []
        for raw_edge in value.get("edges", []):
            edge = (
                dict(raw_edge)
                if isinstance(raw_edge, Mapping)
                else raw_edge.model_dump()
                if isinstance(raw_edge, BaseModel)
                else None
            )
            if edge is None:
                migrated_edges.append(raw_edge)
                continue
            source_type = module_by_id.get(edge.get("source"))
            target_type = module_by_id.get(edge.get("target"))
            if source_type == "query_input" and target_type in {
                "reader",
                "answer_cache_writer",
            }:
                continue
            if source_type == "query_input" and target_type == "decomposer":
                if edge.get("source_output") in {None, "question_text"}:
                    edge["source_output"] = "query_context"
                if edge.get("target_input") in {None, "question_text"}:
                    edge["target_input"] = "query_context"
            migrated_edges.append(edge)
        return {**value, "edges": migrated_edges}


class WorkflowSaveRequest(StrictModel):
    name: str = Field(default="Untitled workflow", min_length=1, max_length=160)
    graph: WorkflowGraph


class WorkflowDocument(StrictModel):
    schema_version: int = 1
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str
    updated_at: str
    graph: WorkflowGraph


class WorkflowExecutionRequest(StrictModel):
    inputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    config_overrides: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "저장된 워크플로를 변경하지 않고 이번 run 스냅샷에만 적용할 "
            "노드별 Config DTO 값입니다."
        ),
    )
    use_cache: bool = True
    cache_only_module_types: Optional[List[str]] = None
    inherit_from_run_id: Optional[str] = Field(
        default=None,
        description=(
            "기존 실행의 완료된 노드 상태를 새 실행으로 복사합니다. "
            "새 노드를 추가해도 이전 결과를 유지하기 위해 사용합니다."
        ),
    )


class RunNodeState(StrictModel):
    node_id: str
    module_type: str
    batch_index: int = Field(ge=0)
    status: NodeStatus = "pending"
    input_payload: Any = None
    config_payload: Dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    error: Optional[str] = None
    cache_key: Optional[str] = None
    cache_hit: bool = False
    outcome: Optional[ExecutionBranch] = None
    skip_reason: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    usage: Optional[Dict[str, int]] = None
    progress: Dict[str, Any] = Field(default_factory=dict)


class RunBatchState(StrictModel):
    index: int = Field(ge=0)
    node_ids: List[str]
    status: BatchStatus = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class RunOrchestrationState(StrictModel):
    """External scheduler identity projected into the product run model."""

    backend: OrchestratorBackend = "direct"
    deployment_name: Optional[str] = None
    external_run_id: Optional[str] = None
    submission_attempt: int = Field(default=0, ge=0)
    submitted_at: Optional[str] = None


class WorkflowRun(StrictModel):
    schema_version: int = 1
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    workflow_id: str = Field(pattern=IDENTIFIER_PATTERN)
    workflow_updated_at: str
    status: RunStatus = "queued"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    graph: WorkflowGraph
    runtime_inputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    use_cache: bool = True
    cache_only_module_types: Optional[List[str]] = None
    orchestration: RunOrchestrationState = Field(
        default_factory=RunOrchestrationState
    )
    batches: List[RunBatchState]
    nodes: Dict[str, RunNodeState]
