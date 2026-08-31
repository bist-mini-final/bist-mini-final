"""Pure workflow run-state transitions."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import RunNodeState, WorkflowRun


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowRunStateReducer:
    """Apply deterministic node, batch and run status transitions."""

    @staticmethod
    def reset_node(state: RunNodeState) -> None:
        state.status = "pending"
        state.input_payload = None
        state.config_payload = {}
        state.output = None
        state.error = None
        state.cache_key = None
        state.cache_hit = False
        state.outcome = None
        state.skip_reason = None
        state.started_at = None
        state.completed_at = None
        state.elapsed_ms = None
        state.cost_usd = None
        state.usage = None
        state.progress = {}

    @staticmethod
    def refresh(run: WorkflowRun) -> None:
        completed_statuses = {"succeeded", "skipped"}
        for batch in run.batches:
            states = [run.nodes[node_id] for node_id in batch.node_ids]
            if any(state.status == "running" for state in states):
                batch.status = "running"
                batch.completed_at = None
            elif any(state.status == "failed" for state in states):
                batch.status = "failed"
                batch.completed_at = _utc_now_iso()
            elif all(state.status in completed_statuses for state in states):
                batch.status = "completed"
                batch.completed_at = _utc_now_iso()
            else:
                batch.status = "pending"
                batch.completed_at = None

        states = list(run.nodes.values())
        if any(state.status == "running" for state in states):
            run.status = "running"
        elif any(state.status == "failed" for state in states):
            run.status = "failed"
        elif all(state.status in completed_statuses for state in states):
            source_node_ids = {edge.source for edge in run.graph.edges}
            sink_node_ids = set(run.nodes) - source_node_ids
            run.status = (
                "completed"
                if any(
                    run.nodes[node_id].status == "succeeded"
                    for node_id in sink_node_ids
                )
                else "failed"
            )
        else:
            run.status = "running" if run.status == "running" else "queued"


__all__ = ["WorkflowRunStateReducer"]
