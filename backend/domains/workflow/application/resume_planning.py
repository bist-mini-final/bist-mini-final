"""Pure planning for resuming failed topological workflow batches."""

from __future__ import annotations

from collections import defaultdict

from backend.domains.workflow.domain import WorkflowRunStateReducer
from backend.domains.workflow.domain.models import WorkflowRun


class WorkflowResumePlanner:
    """Reset failed siblings and their non-terminal descendants for retry."""

    @staticmethod
    def prepare(run: WorkflowRun) -> WorkflowRun:
        failed_node_ids = {
            node_id for node_id, state in run.nodes.items() if state.status == "failed"
        }
        reset_node_ids = WorkflowResumePlanner._failed_batch_nodes(
            run,
            failed_node_ids,
        )
        WorkflowResumePlanner._include_descendants(run, reset_node_ids)
        WorkflowResumePlanner._reset_execution_state(run, reset_node_ids)
        return run

    @staticmethod
    def _failed_batch_nodes(
        run: WorkflowRun,
        failed_node_ids: set[str],
    ) -> set[str]:
        reset_node_ids = set(failed_node_ids)
        for batch in run.batches:
            if any(node_id in failed_node_ids for node_id in batch.node_ids):
                reset_node_ids.update(
                    node_id
                    for node_id in batch.node_ids
                    if run.nodes[node_id].status != "succeeded"
                )
        return reset_node_ids

    @staticmethod
    def _include_descendants(run: WorkflowRun, reset_node_ids: set[str]) -> None:
        outgoing: dict[str, set[str]] = defaultdict(set)
        for edge in run.graph.edges:
            outgoing[edge.source].add(edge.target)
        pending_ancestors = list(reset_node_ids)
        while pending_ancestors:
            node_id = pending_ancestors.pop()
            for descendant_id in outgoing.get(node_id, set()):
                descendant = run.nodes[descendant_id]
                if descendant_id not in reset_node_ids and descendant.status != "succeeded":
                    reset_node_ids.add(descendant_id)
                    pending_ancestors.append(descendant_id)

    @staticmethod
    def _reset_execution_state(run: WorkflowRun, reset_node_ids: set[str]) -> None:
        for node_id in reset_node_ids:
            WorkflowRunStateReducer.reset_node(run.nodes[node_id])
        for batch in run.batches:
            if any(node_id in reset_node_ids for node_id in batch.node_ids):
                batch.status = "pending"
                batch.started_at = None
                batch.completed_at = None
        if reset_node_ids:
            WorkflowRunStateReducer.refresh(run)


__all__ = ["WorkflowResumePlanner"]
