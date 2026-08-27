"""Real PostgreSQL contract for HTTP registration, worker execution, and SSE.

This test is deliberately opt-in for developer machines. CI supplies an isolated
PostgreSQL service through ``INTEGRATION_DATABASE_URL`` and cleans the one exact
run record that it created.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.workflow_routes import create_workflow_router
from backend.engine.orchestration.kubernetes import KubernetesQueueDispatcher
from backend.engine.worker.main import run_one
from backend.engine.workflows.executor import WorkflowExecutor
from backend.engine.workflows.service import WorkflowExecutionService
from backend.engine.workflows.store import ResultCache, RunStore, WorkflowStore
from backend.storage.db_manager import DatabaseManager
from tests.modules.registry_factory import create_test_registry

INTEGRATION_DATABASE_URL = os.getenv("INTEGRATION_DATABASE_URL")


@unittest.skipUnless(
    INTEGRATION_DATABASE_URL,
    "set INTEGRATION_DATABASE_URL to run the PostgreSQL queue integration test",
)
class WorkflowHttpQueueSseIntegrationTests(unittest.TestCase):
    def test_http_queue_worker_and_sse_reach_a_completed_terminal_state(self) -> None:
        assert INTEGRATION_DATABASE_URL is not None
        database = DatabaseManager(INTEGRATION_DATABASE_URL)
        self.assertTrue(database.is_connected())
        workflow_id = f"queue-sse-{uuid4().hex}"
        queue_name = f"queue-sse-{uuid4().hex[:12]}"
        run_id: str | None = None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_store = RunStore(root / "runs", db_manager=database, require_database=True)
            registry = create_test_registry(
                db_manager=database,
                artifact_dir=root / "artifacts",
            )
            executor = WorkflowExecutor(registry, run_store, ResultCache(root / "cache"))
            dispatcher = KubernetesQueueDispatcher(executor, run_store, queue_name)
            workflow_execution = WorkflowExecutionService(
                WorkflowStore(root / "workflows"),
                run_store,
                executor,
                dispatcher,
            )
            app = FastAPI()
            app.include_router(
                create_workflow_router(
                    workflow_store=workflow_execution.workflow_store,
                    run_store=run_store,
                    workflow_execution=workflow_execution,
                ),
                prefix="/api/v1",
            )
            client = TestClient(app)

            try:
                create_response = client.put(
                    f"/api/v1/workflows/{workflow_id}",
                    json={
                        "name": "HTTP queue and SSE contract",
                        "graph": {
                            "nodes": [
                                {
                                    "id": "question",
                                    "module_type": "query_input",
                                    "position": {"x": 0, "y": 0},
                                }
                            ],
                            "edges": [],
                        },
                    },
                )
                self.assertEqual(create_response.status_code, 200)

                submit_response = client.post(
                    f"/api/v1/workflows/{workflow_id}/runs",
                    json={"inputs": {"question": {"query": "HTTP 큐 SSE 계약"}}},
                )
                self.assertEqual(submit_response.status_code, 202)
                run_id = submit_response.json()["id"]
                self.assertEqual(submit_response.json()["status"], "queued")
                self.assertEqual(
                    submit_response.json()["orchestration"]["deployment_name"],
                    queue_name,
                )

                worker_services = SimpleNamespace(
                    db_manager=database,
                    run_store=run_store,
                    workflow_executor=executor,
                    module_registry=registry,
                )
                with patch(
                    "backend.engine.worker.main.runtime_services",
                    return_value=worker_services,
                ):
                    self.assertEqual(
                        run_one(
                            queue_name,
                            "http-queue-sse-contract-worker",
                            heartbeat_seconds=0.01,
                        ),
                        run_id,
                    )

                completed = client.get(f"/api/v1/runs/{run_id}")
                self.assertEqual(completed.status_code, 200)
                self.assertEqual(completed.json()["status"], "completed")
                self.assertEqual(completed.json()["nodes"]["question"]["status"], "succeeded")

                with client.stream("GET", f"/api/v1/runs/{run_id}/stream") as stream:
                    self.assertEqual(stream.status_code, 200)
                    events = "".join(stream.iter_text())
                self.assertIn("event: run_started", events)
                self.assertIn("event: node_completed", events)
                self.assertIn("event: run_finished", events)
                self.assertIn(run_id, events)
            finally:
                if run_id is not None:
                    database.delete_workflow_run(run_id)


if __name__ == "__main__":
    unittest.main()
