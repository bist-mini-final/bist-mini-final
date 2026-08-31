from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.workflow.application.execution_service import WorkflowExecutionService
from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.domain.models import (
    CanvasPosition,
    RunBatchState,
    RunNodeState,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
    WorkflowSaveRequest,
    utc_now_iso,
)
from backend.domains.workflow.infrastructure.job_catalog import canonical_workflow
from backend.domains.workflow.infrastructure.kubernetes import KubernetesQueueDispatcher
from backend.domains.workflow.infrastructure.persistence import ResultCache, RunStore, WorkflowStore
from backend.domains.workflow.presentation import create_workflow_router
from tests.modules.registry_factory import create_test_registry


class RecordingDatabase:
    def __init__(self) -> None:
        self.saved: WorkflowRun | None = None
        self.saved_nodes: list[str] = []
        self.enqueue_count = 0
        self.fail_progress = False

    def is_connected(self) -> bool:
        return True

    def save_workflow_run(
        self,
        run: WorkflowRun,
        *,
        lease_token: str | None = None,
    ) -> None:
        del lease_token
        self.saved = run

    def save_workflow_node_state(
        self,
        run: WorkflowRun,
        node_id: str,
        *,
        lease_token: str | None = None,
    ) -> None:
        del lease_token
        self.saved = run
        self.saved_nodes.append(node_id)

    def save_workflow_node_progress(
        self,
        run: WorkflowRun,
        node_id: str,
        *,
        lease_token: str | None = None,
    ) -> None:
        del lease_token, node_id
        if self.fail_progress:
            raise RuntimeError("database unavailable")
        self.saved = run

    def get_workflow_run(self, run_id: str) -> dict[str, Any] | None:
        if self.saved is None or self.saved.id != run_id:
            return None
        return self.saved.model_dump(mode="json")

    def get_workflow_run_summary(self, run_id: str) -> dict[str, Any] | None:
        return self.get_workflow_run(run_id)

    def get_workflow_node_execution_log(
        self,
        run_id: str,
        node_id: str,
    ) -> dict[str, Any] | None:
        if self.saved is None or self.saved.id != run_id:
            return None
        state = self.saved.nodes.get(node_id)
        if state is None:
            return None
        return state.model_dump(mode="json")

    def enqueue_workflow_run(
        self,
        run_id: str,
        queue_name: str,
        *,
        submission_attempt: int,
        submitted_at: str,
        priority: int = 0,
    ) -> bool:
        del priority
        if self.saved is None or self.saved.id != run_id:
            return False
        self.enqueue_count += 1
        self.saved = self.saved.model_copy(
            update={
                "status": "queued",
                "orchestration": self.saved.orchestration.model_copy(
                    update={
                        "backend": "kubernetes",
                        "deployment_name": queue_name,
                        "submission_attempt": submission_attempt,
                        "submitted_at": submitted_at,
                    }
                ),
            }
        )
        return True


class RecordingDispatcher:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, run_id: str, *, resume_failed: bool = False) -> bool:
        del resume_failed
        self.submitted.append(run_id)
        return True

    def cancel_all(self) -> int:
        return 0

    def is_active(self, run_id: str) -> bool:
        del run_id
        return False


def workflow_run_with_output(output: Any) -> WorkflowRun:
    node = WorkflowNode(
        id="query",
        module_type="query_input",
        position=CanvasPosition(x=0, y=0),
    )
    now = utc_now_iso()
    return WorkflowRun(
        id="run-artifact-test",
        workflow_id="rag_query",
        workflow_updated_at=now,
        status="completed",
        created_at=now,
        updated_at=now,
        graph=WorkflowGraph(nodes=[node], edges=[]),
        batches=[RunBatchState(index=0, node_ids=[node.id], status="completed")],
        nodes={
            node.id: RunNodeState(
                node_id=node.id,
                module_type=node.module_type,
                batch_index=0,
                status="succeeded",
                input_payload={"query": "현재 질문"},
                config_payload={"mode": "current"},
                output=output,
            )
        },
    )


class KubernetesWorkflowContractTests(unittest.TestCase):
    def test_production_run_store_requires_postgresql(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "PostgreSQL 연결"):
            RunStore(require_database=True)

    def test_progress_persistence_failure_is_not_silenced(self) -> None:
        database = RecordingDatabase()
        store = RunStore(repository=database, require_database=True)
        run = store.save(workflow_run_with_output(None))
        database.fail_progress = True

        with self.assertRaisesRegex(RuntimeError, "진행률"):
            store.save_progress(run, "query")

    def test_canonical_jobs_cannot_be_overwritten_or_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = WorkflowStore(Path(directory))
            workflow = canonical_workflow("excel_ingestion")
            self.assertIsNotNone(workflow)
            assert workflow is not None
            request = WorkflowSaveRequest(name="override", graph=workflow.graph)

            with self.assertRaisesRegex(ValueError, "canonical workflow"):
                store.save("excel_ingestion", request)
            with self.assertRaises(ValueError):
                store.delete("excel_ingestion")

            self.assertEqual(
                store.load("excel_ingestion").graph,
                workflow.graph,
            )

    def test_workflow_list_serializes_backend_owned_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_store = WorkflowStore(root / "workflows")
            rag_workflow = canonical_workflow("rag_query")
            self.assertIsNotNone(rag_workflow)
            assert rag_workflow is not None
            workflow_store.save(
                "user-workflow",
                WorkflowSaveRequest(name="사용자 워크플로", graph=rag_workflow.graph),
            )
            app = FastAPI()
            app.include_router(
                create_workflow_router(
                    workflow_store=workflow_store,
                    run_store=RunStore(root / "runs"),
                    workflow_execution=object(),  # type: ignore[arg-type]
                )
            )

            response = TestClient(app).get("/workflows")

        self.assertEqual(response.status_code, 200)
        workflows = {item["id"]: item for item in response.json()["workflows"]}
        self.assertEqual(workflows["rag_query"]["kind"], "standard")
        self.assertFalse(workflows["rag_query"]["editable"])
        self.assertTrue(workflows["rag_query"]["template"])
        self.assertEqual(len(workflows["rag_query"]["graph"]["nodes"]), 9)
        self.assertEqual(len(workflows["rag_query"]["graph"]["edges"]), 9)
        self.assertEqual(workflows["bi_metric_extraction"]["kind"], "standard")
        self.assertFalse(workflows["bi_metric_extraction"]["template"])
        self.assertEqual(workflows["user-workflow"]["kind"], "user")
        self.assertTrue(workflows["user-workflow"]["editable"])
        self.assertFalse(workflows["user-workflow"]["template"])

    def test_run_list_serializes_workflow_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_store = RunStore(root / "runs")
            run_store.save(workflow_run_with_output({"answer": "ok"}))
            app = FastAPI()
            app.include_router(
                create_workflow_router(
                    workflow_store=WorkflowStore(root / "workflows"),
                    run_store=run_store,
                    workflow_execution=object(),  # type: ignore[arg-type]
                )
            )

            response = TestClient(app).get("/runs?workflow_id=rag_query")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["runs"][0]["id"], "run-artifact-test")

    def test_node_detail_endpoint_returns_current_dto_values(self) -> None:
        database = RecordingDatabase()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_store = RunStore(root / "runs", repository=database)
            run_store.save(workflow_run_with_output({"answer": "현재 답변"}))
            app = FastAPI()
            app.include_router(
                create_workflow_router(
                    workflow_store=WorkflowStore(root / "workflows"),
                    run_store=run_store,
                    workflow_execution=object(),  # type: ignore[arg-type]
                )
            )

            response = TestClient(app).get(
                "/runs/run-artifact-test/nodes/query"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["input_payload"], {"query": "현재 질문"})
        self.assertEqual(response.json()["config_payload"], {"mode": "current"})
        self.assertEqual(response.json()["output"], {"answer": "현재 답변"})

    def test_large_node_output_is_externalized_and_hydrated(self) -> None:
        database = RecordingDatabase()
        large_output = {"payload": "x" * (140 * 1024)}
        with tempfile.TemporaryDirectory() as directory:
            run_directory = Path(directory)
            store = RunStore(run_directory, repository=database)
            store.save(workflow_run_with_output(large_output))

            self.assertIsNotNone(database.saved)
            assert database.saved is not None
            persisted = database.saved.nodes["query"].output
            self.assertIn("_workflow_artifact", persisted)
            self.assertEqual(
                len(list((run_directory / "artifacts").glob("*.json.gz"))),
                1,
            )

            reloaded = RunStore(run_directory, repository=database).load(
                "run-artifact-test"
            )
            self.assertEqual(reloaded.nodes["query"].output, large_output)

    def test_terminal_node_save_uses_partial_database_write(self) -> None:
        database = RecordingDatabase()
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory), repository=database)
            run = workflow_run_with_output({"answer": "ok"})
            store.save_node(run, "query")

        self.assertEqual(database.saved_nodes, ["query"])

    def test_kubernetes_submission_is_idempotent(self) -> None:
        database = RecordingDatabase()
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory), repository=database)
            run = workflow_run_with_output(None).model_copy(
                update={"status": "queued"}
            )
            store.save(run)
            dispatcher = KubernetesQueueDispatcher(
                executor=object(),  # type: ignore[arg-type]
                run_store=store,
                queue_name="workflow-core",
            )

            self.assertTrue(dispatcher.submit(run.id))
            self.assertFalse(dispatcher.submit(run.id))

        self.assertEqual(database.enqueue_count, 1)

    def test_api_accepts_run_only_through_durable_queue_boundary(self) -> None:
        database = RecordingDatabase()
        dispatcher = RecordingDispatcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_store = RunStore(root / "runs", repository=database)
            registry = create_test_registry()
            executor = WorkflowExecutor(registry, run_store, ResultCache(root / "cache"))
            workflow_store = WorkflowStore(root / "workflows")
            app = FastAPI()
            app.include_router(
                create_workflow_router(
                    workflow_store=workflow_store,
                    run_store=run_store,
                    workflow_execution=WorkflowExecutionService(
                        workflow_store,
                        run_store,
                        executor,
                        dispatcher,  # type: ignore[arg-type]
                    ),
                )
            )
            response = TestClient(app).post(
                "/workflows/rag_query/runs",
                json={"inputs": {"query": {"query": "삼성전자 매출"}}},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(dispatcher.submitted), 1)
        self.assertEqual(response.json()["id"], dispatcher.submitted[0])

    def test_api_rejects_submission_without_postgresql(self) -> None:
        dispatcher = RecordingDispatcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_store = RunStore(root / "runs")
            executor = WorkflowExecutor(
                create_test_registry(),
                run_store,
                ResultCache(root / "cache"),
            )
            workflow_store = WorkflowStore(root / "workflows")
            app = FastAPI()
            app.include_router(
                create_workflow_router(
                    workflow_store=workflow_store,
                    run_store=run_store,
                    workflow_execution=WorkflowExecutionService(
                        workflow_store,
                        run_store,
                        executor,
                        dispatcher,  # type: ignore[arg-type]
                    ),
                )
            )
            response = TestClient(app).post(
                "/workflows/rag_query/runs",
                json={"inputs": {"query": {"query": "삼성전자 매출"}}},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(dispatcher.submitted, [])
        self.assertEqual(
            response.json()["detail"]["code"],
            "WORKFLOW_QUEUE_UNAVAILABLE",
        )


if __name__ == "__main__":
    unittest.main()
