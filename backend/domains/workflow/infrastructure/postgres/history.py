"""Workflow run recovery listings and node execution history capability."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .capabilities import WorkflowDatabaseCapability


class WorkflowRunHistoryRepositoryMixin(WorkflowDatabaseCapability):
    """Read and delete workflow run history and node execution records."""

    def list_workflow_runs(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List workflow runs from database, ordered by most recently updated."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if workflow_id is not None:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, workflow_updated_at, status, schema_version,
                               graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                               created_at, updated_at
                        FROM workflow_runs
                        WHERE workflow_id = %s
                        ORDER BY updated_at DESC;
                        """,
                        (workflow_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, workflow_updated_at, status, schema_version,
                               graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                               created_at, updated_at
                        FROM workflow_runs
                        ORDER BY updated_at DESC;
                        """
                    )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "workflow_id": row[1],
                        "workflow_updated_at": row[2] or "",
                        "status": row[3],
                        "schema_version": row[4],
                        "graph": row[5] or {},
                        "runtime_inputs": row[6] or {},
                        "use_cache": bool(row[7]),
                        "orchestration": row[8] or {},
                        "batches": row[9] or [],
                        "nodes": row[10] or {},
                        "created_at": row[11].isoformat()
                        if hasattr(row[11], "isoformat")
                        else str(row[11]),
                        "updated_at": row[12].isoformat()
                        if hasattr(row[12], "isoformat")
                        else str(row[12]),
                    }
                    for row in rows
                ]
        finally:
            conn.close()

    def list_pending_workflow_run_ids(
        self,
        workflow_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Return only IDs needed for startup recovery without loading node payloads."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if workflow_ids is None:
                    cur.execute(
                        """
                        SELECT run_id
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                        ORDER BY created_at ASC;
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT run_id
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                          AND workflow_id = ANY(%s)
                        ORDER BY created_at ASC;
                        """,
                        (workflow_ids,),
                    )
                return [str(row[0]) for row in cur.fetchall()]
        finally:
            conn.close()

    def list_pending_workflow_run_references(
        self,
        workflow_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return lightweight recovery metadata without graph or node JSONB."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if workflow_ids is None:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, status, orchestration
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                        ORDER BY created_at ASC;
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, status, orchestration
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                          AND workflow_id = ANY(%s)
                        ORDER BY created_at ASC;
                        """,
                        (workflow_ids,),
                    )
                return [
                    {
                        "run_id": str(row[0]),
                        "workflow_id": str(row[1]),
                        "status": str(row[2]),
                        "orchestration": row[3] or {},
                    }
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()

    def delete_workflow_run(self, run_id: str) -> bool:
        """Delete a workflow run and cascade-delete associated node logs."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workflow_runs WHERE run_id = %s;", (run_id,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    def clear_workflow_runs(self) -> int:
        """Delete all workflow runs from database."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workflow_runs;")
                count = cur.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    @staticmethod
    def _node_execution_log_from_row(row: Any) -> Dict[str, Any]:
        """Convert a full node execution row into the runtime DTO shape."""

        return {
            "log_id": row[0],
            "run_id": row[1],
            "node_id": row[2],
            "module_type": row[3],
            "batch_index": row[4],
            "status": row[5],
            "input_payload": row[6],
            "config_payload": row[7] or {},
            "output": row[8],
            "error": row[9],
            "cache_hit": bool(row[10]),
            "outcome": row[11],
            "progress": row[12] or {},
            "elapsed_ms": row[13],
            "cost_usd": row[14],
            "usage": row[15],
            "started_at": row[16].isoformat()
            if hasattr(row[16], "isoformat")
            else str(row[16])
            if row[16]
            else None,
            "completed_at": row[17].isoformat()
            if hasattr(row[17], "isoformat")
            else str(row[17])
            if row[17]
            else None,
            "created_at": row[18].isoformat() if hasattr(row[18], "isoformat") else str(row[18]),
        }

    def get_workflow_node_execution_log(
        self,
        run_id: str,
        node_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load one node's complete current DTO state for the settings monitor."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT log_id, run_id, node_id, module_type, batch_index,
                           status, input_payload, config_payload, output, error,
                           cache_hit, outcome, progress, elapsed_ms, cost_usd,
                           usage, started_at, completed_at, created_at
                    FROM node_execution_logs
                    WHERE run_id = %s AND node_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (run_id, node_id),
                )
                row = cur.fetchone()
            return self._node_execution_log_from_row(row) if row else None
        finally:
            conn.close()

    def get_node_execution_logs(self, run_id: str) -> List[Dict[str, Any]]:
        """Get execution logs for all nodes of a given workflow run."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT log_id, run_id, node_id, module_type, batch_index,
                           status, input_payload, config_payload, output, error,
                           cache_hit, outcome, progress, elapsed_ms, cost_usd,
                           usage, started_at, completed_at, created_at
                    FROM node_execution_logs
                    WHERE run_id = %s
                    ORDER BY batch_index ASC, created_at ASC;
                    """,
                    (run_id,),
                )
                rows = cur.fetchall()
                return [self._node_execution_log_from_row(row) for row in rows]
        finally:
            conn.close()


__all__ = ["WorkflowRunHistoryRepositoryMixin"]
