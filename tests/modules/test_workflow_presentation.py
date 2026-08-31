from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

from backend.api.workflow_controller import workflow_run_events
from backend.engine.workflows.models import (
    CanvasPosition,
    NodeStatus,
    RunBatchState,
    RunNodeState,
    RunStatus,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
    utc_now_iso,
)
from backend.shared.application.state_stream import SharedStateStream


def _run(
    *,
    status: RunStatus,
    node_status: NodeStatus,
    updated_at: str,
) -> WorkflowRun:
    node = WorkflowNode(
        id="query",
        module_type="query_input",
        position=CanvasPosition(x=0, y=0),
    )
    return WorkflowRun.model_validate(
        {
            "id": "run-events",
            "workflow_id": "rag_query",
            "workflow_updated_at": updated_at,
            "status": status,
            "created_at": updated_at,
            "updated_at": updated_at,
            "graph": WorkflowGraph(nodes=[node], edges=[]),
            "batches": [
                RunBatchState(
                    index=0,
                    node_ids=[node.id],
                    status="completed" if status == "completed" else "running",
                )
            ],
            "nodes": {
                node.id: RunNodeState(
                    node_id=node.id,
                    module_type=node.module_type,
                    batch_index=0,
                    status=node_status,
                    output={"answer": "ok"} if node_status == "succeeded" else None,
                )
            },
        }
    )


class _Stream:
    def __init__(self, runs: list[WorkflowRun]) -> None:
        self._runs = runs

    async def subscribe(
        self,
        key: str,
        *,
        initial: WorkflowRun | None = None,
    ) -> AsyncIterator[WorkflowRun]:
        del key, initial
        for run in self._runs:
            yield run


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def test_workflow_event_presenter_emits_only_state_transitions() -> None:
    now = utc_now_iso()
    running = _run(status="running", node_status="running", updated_at=now)
    completed = _run(
        status="completed",
        node_status="succeeded",
        updated_at=now,
    )
    stream = cast(
        SharedStateStream[str, WorkflowRun],
        cast(Any, _Stream([running, running, completed])),
    )

    async def collect() -> list[str]:
        return [
            event["event"]
            async for event in workflow_run_events(
                stream,
                running.id,
                running,
                cast(Any, _ConnectedRequest()),
            )
        ]

    assert asyncio.run(collect()) == [
        "run_started",
        "node_started",
        "node_completed",
        "run_finished",
    ]
