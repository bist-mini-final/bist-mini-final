from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
ExecutionBranch = Literal["generated", "cached", "failed"]
OutputBranch = Literal["generated", "cached"]
NodeStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
RunStatus = Literal["queued", "running", "completed", "failed"]
BatchStatus = Literal["pending", "running", "completed", "failed"]


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
    use_cache: bool = True


class RunNodeState(StrictModel):
    node_id: str
    module_type: str
    batch_index: int = Field(ge=0)
    status: NodeStatus = "pending"
    input_payload: Any = None
    output: Any = None
    error: Optional[str] = None
    cache_key: Optional[str] = None
    cache_hit: bool = False
    outcome: Optional[ExecutionBranch] = None
    skip_reason: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class RunBatchState(StrictModel):
    index: int = Field(ge=0)
    node_ids: List[str]
    status: BatchStatus = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


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
    batches: List[RunBatchState]
    nodes: Dict[str, RunNodeState]
