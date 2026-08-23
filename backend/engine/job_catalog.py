"""Project pure ``jobs`` definitions into backend workflow documents."""

from __future__ import annotations

from typing import Iterable, Optional

from backend.engine.workflows.models import (
    CanvasPosition,
    WorkflowDocument,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
)
from jobs import ALL_JOBS, DagJobDefinition

CANONICAL_UPDATED_AT = "2026-08-23T00:00:00+00:00"
_CANONICAL_JOBS = tuple(
    job for job in ALL_JOBS if isinstance(job, DagJobDefinition)
)


def workflow_from_job(
    job: DagJobDefinition,
    *,
    workflow_id: Optional[str] = None,
) -> WorkflowDocument:
    """Convert one portable Job DAG to the persisted workflow API model."""

    nodes = []
    for index, node in enumerate(job.nodes):
        column = index % 4
        row = index // 4
        nodes.append(
            WorkflowNode(
                id=node.node_id,
                module_type=node.module_type,
                position=CanvasPosition(x=80 + column * 420, y=80 + row * 360),
                config=dict(node.config),
                values=dict(node.values),
            )
        )
    return WorkflowDocument(
        id=workflow_id or job.job_id,
        name=job.name,
        updated_at=CANONICAL_UPDATED_AT,
        graph=WorkflowGraph(
            nodes=nodes,
            edges=[
                WorkflowEdge(
                    id=edge.edge_id,
                    source=edge.source,
                    target=edge.target,
                    source_output=edge.source_output,
                    target_input=edge.target_input,
                    source_branch=edge.source_branch,
                )
                for edge in job.edges
            ],
        ),
    )


def canonical_workflow(workflow_id: str) -> Optional[WorkflowDocument]:
    """Return the canonical workflow for an exact current job identifier."""

    job = next((item for item in _CANONICAL_JOBS if item.job_id == workflow_id), None)
    return workflow_from_job(job) if job is not None else None


def canonical_workflows() -> Iterable[WorkflowDocument]:
    """Return canonical workflows exposed by the product API."""

    return tuple(workflow_from_job(job) for job in _CANONICAL_JOBS)


__all__ = ["canonical_workflow", "canonical_workflows", "workflow_from_job"]
