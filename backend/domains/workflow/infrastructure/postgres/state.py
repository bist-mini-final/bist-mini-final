"""Workflow run and node-state persistence capability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2.extras

from .capabilities import WorkflowDatabaseCapability
from .queue import WorkflowLeaseLost


class WorkflowRunStateRepositoryMixin(WorkflowDatabaseCapability):
    """Persist and project current workflow and node execution state."""

    def save_workflow_run(
        self,
        run_dict_or_model: Any,
        *,
        lease_token: Optional[str] = None,
    ) -> None:
        """Insert or update a workflow run and its node execution logs."""
        if hasattr(run_dict_or_model, "model_dump"):
            data = run_dict_or_model.model_dump(mode="json")
        else:
            data = dict(run_dict_or_model)

        run_id = data.get("id") or data.get("run_id")
        if not run_id:
            raise ValueError("run_id is required to save workflow run")

        workflow_id = data.get("workflow_id", "")
        workflow_updated_at = data.get("workflow_updated_at", "")
        status = data.get("status", "queued")
        schema_version = data.get("schema_version", 2)
        graph = data.get("graph", {})
        runtime_inputs = data.get("runtime_inputs", {})
        use_cache = bool(data.get("use_cache", True))
        orchestration = data.get("orchestration", {})
        batches = data.get("batches", [])
        nodes = data.get("nodes", {})
        created_at = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        updated_at = data.get("updated_at") or datetime.now(timezone.utc).isoformat()

        failed_state = next(
            (st for st in nodes.values() if isinstance(st, dict) and st.get("status") == "failed"),
            None,
        )
        error_message = failed_state.get("error") if failed_state else None

        completed_at = None
        if status in ("completed", "failed"):
            completed_at = updated_at

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if lease_token is not None:
                    cur.execute(
                        """
                        SELECT 1
                        FROM workflow_runs
                        WHERE run_id = %s AND lease_token = %s
                        FOR UPDATE;
                        """,
                        (run_id, lease_token),
                    )
                    if cur.fetchone() is None:
                        raise WorkflowLeaseLost(f"워크플로 lease 소유권을 잃었습니다: {run_id}")
                cur.execute(
                    """
                    INSERT INTO workflow_runs (
                        run_id, workflow_id, workflow_updated_at, status, schema_version,
                        graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                        error_message, created_at, updated_at, completed_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (run_id) DO UPDATE SET
                        workflow_id = EXCLUDED.workflow_id,
                        workflow_updated_at = EXCLUDED.workflow_updated_at,
                        status = CASE
                            WHEN workflow_runs.cancel_requested
                                 AND EXCLUDED.status IN ('queued', 'running')
                            THEN 'paused'
                            ELSE EXCLUDED.status
                        END,
                        schema_version = EXCLUDED.schema_version,
                        graph = EXCLUDED.graph,
                        runtime_inputs = EXCLUDED.runtime_inputs,
                        use_cache = EXCLUDED.use_cache,
                        orchestration = EXCLUDED.orchestration,
                        batches = EXCLUDED.batches,
                        nodes = EXCLUDED.nodes,
                        error_message = EXCLUDED.error_message,
                        updated_at = EXCLUDED.updated_at,
                        completed_at = EXCLUDED.completed_at;
                    """,
                    (
                        run_id,
                        workflow_id,
                        workflow_updated_at,
                        status,
                        schema_version,
                        psycopg2.extras.Json(graph),
                        psycopg2.extras.Json(runtime_inputs),
                        use_cache,
                        psycopg2.extras.Json(orchestration),
                        psycopg2.extras.Json(batches),
                        psycopg2.extras.Json(nodes),
                        error_message,
                        created_at,
                        updated_at,
                        completed_at,
                    ),
                )

                for node_id, node_state in nodes.items():
                    if not isinstance(node_state, dict):
                        continue
                    log_id = f"{run_id}:{node_id}"
                    module_type = node_state.get("module_type", "")
                    node_status = node_state.get("status", "pending")
                    input_payload = node_state.get("input_payload")
                    config_payload = node_state.get("config_payload") or {}
                    output = node_state.get("output")
                    error = node_state.get("error")
                    cache_hit = bool(node_state.get("cache_hit", False))
                    outcome = node_state.get("outcome")
                    progress = node_state.get("progress") or {}
                    batch_index = node_state.get("batch_index", 0)
                    elapsed_ms = node_state.get("elapsed_ms")
                    cost_usd = node_state.get("cost_usd")
                    usage = node_state.get("usage")
                    started_at = node_state.get("started_at")
                    node_completed_at = node_state.get("completed_at")

                    cur.execute(
                        """
                        INSERT INTO node_execution_logs (
                            log_id, run_id, node_id, module_type, batch_index,
                            status, input_payload, config_payload, output, error,
                            cache_hit, outcome, progress, elapsed_ms, cost_usd,
                            usage, started_at, completed_at, created_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, NOW()
                        )
                        ON CONFLICT (log_id) DO UPDATE SET
                            module_type = EXCLUDED.module_type,
                            batch_index = EXCLUDED.batch_index,
                            status = EXCLUDED.status,
                            input_payload = EXCLUDED.input_payload,
                            config_payload = EXCLUDED.config_payload,
                            output = EXCLUDED.output,
                            error = EXCLUDED.error,
                            cache_hit = EXCLUDED.cache_hit,
                            outcome = EXCLUDED.outcome,
                            progress = EXCLUDED.progress,
                            elapsed_ms = EXCLUDED.elapsed_ms,
                            cost_usd = EXCLUDED.cost_usd,
                            usage = EXCLUDED.usage,
                            started_at = EXCLUDED.started_at,
                            completed_at = EXCLUDED.completed_at;
                        """,
                        (
                            log_id,
                            run_id,
                            node_id,
                            module_type,
                            batch_index,
                            node_status,
                            psycopg2.extras.Json(input_payload)
                            if input_payload is not None
                            else None,
                            psycopg2.extras.Json(config_payload),
                            psycopg2.extras.Json(output) if output is not None else None,
                            error,
                            cache_hit,
                            outcome,
                            psycopg2.extras.Json(progress),
                            elapsed_ms,
                            cost_usd,
                            psycopg2.extras.Json(usage) if usage is not None else None,
                            started_at,
                            node_completed_at,
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    def get_workflow_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Load a full workflow run from database by run_id."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, workflow_id, workflow_updated_at, status, schema_version,
                           graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                           created_at, updated_at
                    FROM workflow_runs
                    WHERE run_id = %s;
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                data = {
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
                cur.execute(
                    """
                    SELECT node_id, module_type, batch_index, status,
                           input_payload, config_payload, output, error,
                           cache_hit, outcome, progress, elapsed_ms, cost_usd,
                           usage, started_at, completed_at
                    FROM node_execution_logs
                    WHERE run_id = %s
                    ORDER BY batch_index ASC, created_at ASC;
                    """,
                    (run_id,),
                )
                node_rows = cur.fetchall()
                if node_rows:
                    persisted_nodes = data["nodes"]
                    data["nodes"] = {
                        str(node_row[0]): {
                            **(
                                persisted_nodes.get(str(node_row[0]), {})
                                if isinstance(persisted_nodes, dict)
                                else {}
                            ),
                            "node_id": node_row[0],
                            "module_type": node_row[1],
                            "batch_index": node_row[2] or 0,
                            "status": node_row[3],
                            "input_payload": node_row[4],
                            "config_payload": node_row[5] or {},
                            "output": node_row[6],
                            "error": node_row[7],
                            "cache_hit": bool(node_row[8]),
                            "outcome": node_row[9],
                            "progress": node_row[10] or {},
                            "elapsed_ms": node_row[11],
                            "cost_usd": node_row[12],
                            "usage": node_row[13],
                            "started_at": (
                                node_row[14].isoformat()
                                if hasattr(node_row[14], "isoformat")
                                else str(node_row[14])
                                if node_row[14]
                                else None
                            ),
                            "completed_at": (
                                node_row[15].isoformat()
                                if hasattr(node_row[15], "isoformat")
                                else str(node_row[15])
                                if node_row[15]
                                else None
                            ),
                        }
                        for node_row in node_rows
                    }
                return data
        finally:
            conn.close()

    @staticmethod
    def _workflow_run_summary_from_row(
        row: Any,
        nodes: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a product-facing run snapshot without loading large node payloads."""

        status = row[3]
        node_statuses = {str(node.get("status")) for node in nodes.values() if node.get("status")}
        if status in ("queued", "running") and node_statuses:
            if node_statuses <= {"succeeded", "skipped"}:
                status = "completed"
            elif "failed" in node_statuses:
                status = "failed"
        return {
            "id": row[0],
            "workflow_id": row[1],
            "workflow_updated_at": row[2] or "",
            "status": status,
            "schema_version": row[4],
            "graph": row[5] or {},
            "runtime_inputs": row[6] or {},
            "use_cache": bool(row[7]),
            "orchestration": row[8] or {},
            "batches": row[9] or [],
            "nodes": nodes,
            "created_at": (row[10].isoformat() if hasattr(row[10], "isoformat") else str(row[10])),
            "updated_at": (row[11].isoformat() if hasattr(row[11], "isoformat") else str(row[11])),
        }

    @staticmethod
    def _node_summary_from_row(row: Any) -> Dict[str, Any]:
        """Convert a lightweight node_execution_logs projection to RunNodeState."""

        return {
            "node_id": row[1],
            "module_type": row[2],
            "batch_index": row[3] or 0,
            "status": row[4],
            "input_payload": None,
            "config_payload": row[5] or {},
            "output": row[6],
            "error": row[7],
            "cache_key": None,
            "cache_hit": bool(row[8]),
            "outcome": row[9],
            "skip_reason": None,
            "progress": row[10] or {},
            "elapsed_ms": row[11],
            "cost_usd": row[12],
            "usage": row[13],
            "started_at": (
                row[14].isoformat()
                if hasattr(row[14], "isoformat")
                else str(row[14])
                if row[14]
                else None
            ),
            "completed_at": (
                row[15].isoformat()
                if hasattr(row[15], "isoformat")
                else str(row[15])
                if row[15]
                else None
            ),
        }

    def _get_workflow_node_summaries(
        self,
        conn: Any,
        run_ids: List[str],
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Load statuses and compact result metadata, never document/vector arrays."""

        if not run_ids:
            return {}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, node_id, module_type, batch_index, status,
                       config_payload,
                       CASE
                           WHEN module_type IN (
                               'processed_file_selector',
                               'luna_vlm_structure_detector',
                               'pgvector_index_writer',
                               'company_entity_extractor',
                               'sheet_metadata_persistence',
                               'query_input',
                               'llm_query_router',
                               'decomposer',
                               'reader'
                           ) THEN output
                           ELSE NULL
                       END AS projected_output,
                       error, cache_hit, outcome, progress, elapsed_ms,
                       cost_usd, usage, started_at, completed_at
                FROM node_execution_logs
                WHERE run_id = ANY(%s)
                ORDER BY run_id, batch_index ASC, created_at ASC;
                """,
                (run_ids,),
            )
            summaries: Dict[str, Dict[str, Dict[str, Any]]] = {run_id: {} for run_id in run_ids}
            for row in cur.fetchall():
                run_id = str(row[0])
                node = self._node_summary_from_row(row)
                summaries.setdefault(run_id, {})[node["node_id"]] = node
            return summaries

    def get_workflow_run_summary(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Load a polling-safe run snapshot without large node inputs or outputs."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, workflow_id, workflow_updated_at, status,
                           schema_version, graph, runtime_inputs, use_cache,
                           orchestration, batches, created_at, updated_at
                    FROM workflow_runs
                    WHERE run_id = %s;
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
            if not row:
                return None
            nodes_by_run = self._get_workflow_node_summaries(conn, [run_id])
            return self._workflow_run_summary_from_row(
                row,
                nodes_by_run.get(run_id, {}),
            )
        finally:
            conn.close()

    def list_workflow_run_summaries(
        self,
        workflow_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List polling-safe run snapshots ordered by most recent update."""

        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT run_id, workflow_id, workflow_updated_at, status,
                           schema_version, graph, runtime_inputs, use_cache,
                           orchestration, batches, created_at, updated_at
                    FROM workflow_runs
                """
                if workflow_id is not None:
                    query += " WHERE workflow_id = %s ORDER BY updated_at DESC"
                    parameters: tuple[object, ...] = (workflow_id,)
                else:
                    query += " ORDER BY updated_at DESC"
                    parameters = ()
                if limit is not None:
                    query += " LIMIT %s"
                    parameters = (*parameters, limit)
                cur.execute(query + ";", parameters)
                rows = cur.fetchall()
            run_ids = [str(row[0]) for row in rows]
            nodes_by_run = self._get_workflow_node_summaries(conn, run_ids)
            return [
                self._workflow_run_summary_from_row(
                    row,
                    nodes_by_run.get(str(row[0]), {}),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def find_ingestion_run_id_by_index(self, index_id: str) -> Optional[str]:
        """Resolve an index to its durable ingestion run without scanning run JSON."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT log.run_id
                    FROM node_execution_logs AS log
                    JOIN workflow_runs AS run ON run.run_id = log.run_id
                    WHERE run.workflow_id = 'excel_ingestion'
                      AND log.module_type = 'pgvector_index_writer'
                      AND (
                          log.output->>'index_id' = %s
                          OR log.progress->>'target_index_id' = %s
                      )
                    ORDER BY log.completed_at DESC NULLS LAST,
                             run.updated_at DESC
                    LIMIT 1;
                    """,
                    (index_id, index_id),
                )
                row = cur.fetchone()
                return str(row[0]) if row else None
        finally:
            conn.close()

    def save_workflow_node_progress(
        self,
        run: Any,
        node_id: str,
        *,
        lease_token: Optional[str] = None,
    ) -> None:
        """Persist one node's live status without retransmitting the full run JSON."""

        if hasattr(run, "model_dump"):
            run_id = getattr(run, "id", None)
            run_status = getattr(run, "status", "running")
            updated_at = getattr(run, "updated_at", None)
            batches = [
                batch.model_dump(mode="json") if hasattr(batch, "model_dump") else dict(batch)
                for batch in getattr(run, "batches", [])
            ]
            raw_node = getattr(run, "nodes", {}).get(node_id)
            node_state = (
                raw_node.model_dump(mode="json")
                if raw_node is not None and hasattr(raw_node, "model_dump")
                else dict(raw_node)
                if raw_node is not None
                else None
            )
        else:
            data = dict(run)
            run_id = data.get("id") or data.get("run_id")
            run_status = data.get("status", "running")
            updated_at = data.get("updated_at")
            batches = data.get("batches") or []
            node_state = (data.get("nodes") or {}).get(node_id)
        if not isinstance(node_state, dict):
            raise ValueError(f"run에 progress 대상 노드가 없습니다: {node_id}")
        if not run_id:
            raise ValueError("run_id is required to save workflow progress")

        updated_at = updated_at or datetime.now(timezone.utc).isoformat()
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = CASE
                            WHEN cancel_requested AND %s IN ('queued', 'running')
                            THEN 'paused'
                            ELSE %s
                        END,
                        batches = %s,
                        updated_at = %s,
                        heartbeat_at = CASE
                            WHEN worker_id IS NOT NULL THEN NOW()
                            ELSE heartbeat_at
                        END
                    WHERE run_id = %s
                      AND lease_token IS NOT DISTINCT FROM %s;
                    """,
                    (
                        run_status,
                        run_status,
                        psycopg2.extras.Json(batches),
                        updated_at,
                        run_id,
                        lease_token,
                    ),
                )
                if cur.rowcount != 1:
                    raise WorkflowLeaseLost(f"워크플로 lease 소유권을 잃었습니다: {run_id}")
                cur.execute(
                    """
                    INSERT INTO node_execution_logs (
                        log_id, run_id, node_id, module_type, batch_index,
                        status, config_payload, error, cache_hit, outcome,
                        progress, elapsed_ms, cost_usd, usage, started_at,
                        completed_at, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, NOW()
                    )
                    ON CONFLICT (log_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        config_payload = EXCLUDED.config_payload,
                        error = EXCLUDED.error,
                        cache_hit = EXCLUDED.cache_hit,
                        outcome = EXCLUDED.outcome,
                        progress = EXCLUDED.progress,
                        elapsed_ms = EXCLUDED.elapsed_ms,
                        cost_usd = EXCLUDED.cost_usd,
                        usage = EXCLUDED.usage,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at;
                    """,
                    (
                        f"{run_id}:{node_id}",
                        run_id,
                        node_id,
                        node_state.get("module_type", ""),
                        node_state.get("batch_index", 0),
                        node_state.get("status", "pending"),
                        psycopg2.extras.Json(node_state.get("config_payload") or {}),
                        node_state.get("error"),
                        bool(node_state.get("cache_hit", False)),
                        node_state.get("outcome"),
                        psycopg2.extras.Json(node_state.get("progress") or {}),
                        node_state.get("elapsed_ms"),
                        node_state.get("cost_usd"),
                        psycopg2.extras.Json(node_state.get("usage"))
                        if node_state.get("usage") is not None
                        else None,
                        node_state.get("started_at"),
                        node_state.get("completed_at"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def save_workflow_node_state(
        self,
        run: Any,
        node_id: str,
        *,
        lease_token: Optional[str] = None,
    ) -> None:
        """Upsert one completed node and run metadata without rewriting the DAG."""

        run_id = getattr(run, "id", None)
        node = getattr(run, "nodes", {}).get(node_id)
        if not run_id or node is None:
            raise ValueError(f"run에 저장할 노드가 없습니다: {node_id}")
        node_state = node.model_dump(mode="json") if hasattr(node, "model_dump") else dict(node)
        batches = [
            batch.model_dump(mode="json") if hasattr(batch, "model_dump") else dict(batch)
            for batch in getattr(run, "batches", [])
        ]
        updated_at = getattr(run, "updated_at", None) or datetime.now(timezone.utc).isoformat()
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = CASE
                            WHEN cancel_requested AND %s IN ('queued', 'running')
                            THEN 'paused'
                            ELSE %s
                        END,
                        batches = %s,
                        error_message = %s,
                        updated_at = %s,
                        completed_at = CASE
                            WHEN %s IN ('completed', 'failed')
                            THEN %s::timestamptz
                            ELSE NULL::timestamptz
                        END,
                        heartbeat_at = NOW()
                    WHERE run_id = %s
                      AND lease_token IS NOT DISTINCT FROM %s;
                    """,
                    (
                        run.status,
                        run.status,
                        psycopg2.extras.Json(batches),
                        node_state.get("error") if node_state.get("status") == "failed" else None,
                        updated_at,
                        run.status,
                        updated_at,
                        run_id,
                        lease_token,
                    ),
                )
                if cur.rowcount != 1:
                    raise WorkflowLeaseLost(f"워크플로 lease 소유권을 잃었습니다: {run_id}")
                cur.execute(
                    """
                    INSERT INTO node_execution_logs (
                        log_id, run_id, node_id, module_type, batch_index,
                        status, input_payload, config_payload, output, error,
                        cache_hit, outcome, progress, elapsed_ms, cost_usd,
                        usage, started_at, completed_at, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, NOW()
                    )
                    ON CONFLICT (log_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        input_payload = EXCLUDED.input_payload,
                        config_payload = EXCLUDED.config_payload,
                        output = EXCLUDED.output,
                        error = EXCLUDED.error,
                        cache_hit = EXCLUDED.cache_hit,
                        outcome = EXCLUDED.outcome,
                        progress = EXCLUDED.progress,
                        elapsed_ms = EXCLUDED.elapsed_ms,
                        cost_usd = EXCLUDED.cost_usd,
                        usage = EXCLUDED.usage,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at;
                    """,
                    (
                        f"{run_id}:{node_id}",
                        run_id,
                        node_id,
                        node_state.get("module_type", ""),
                        node_state.get("batch_index", 0),
                        node_state.get("status", "pending"),
                        psycopg2.extras.Json(node_state.get("input_payload"))
                        if node_state.get("input_payload") is not None
                        else None,
                        psycopg2.extras.Json(node_state.get("config_payload") or {}),
                        psycopg2.extras.Json(node_state.get("output"))
                        if node_state.get("output") is not None
                        else None,
                        node_state.get("error"),
                        bool(node_state.get("cache_hit", False)),
                        node_state.get("outcome"),
                        psycopg2.extras.Json(node_state.get("progress") or {}),
                        node_state.get("elapsed_ms"),
                        node_state.get("cost_usd"),
                        psycopg2.extras.Json(node_state.get("usage"))
                        if node_state.get("usage") is not None
                        else None,
                        node_state.get("started_at"),
                        node_state.get("completed_at"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


__all__ = ["WorkflowRunStateRepositoryMixin"]
