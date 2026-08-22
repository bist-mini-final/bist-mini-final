from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.engine.orchestration import CompiledTaskNode, compile_task_plan
from backend.engine.workflows.models import (
    CanvasPosition,
    RunBatchState,
    RunNodeState,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
    utc_now_iso,
)
from backend.engine.worker.main import execute_with_policy, run_one, runtime_services


class WorkflowWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.node = WorkflowNode(
            id="q1",
            module_type="query_input",
            position=CanvasPosition(x=0.0, y=0.0),
            config={},
            values={"question_text": "삼성전자 매출"},
        )
        self.graph = WorkflowGraph(nodes=[self.node], edges=[])
        self.run = WorkflowRun(
            id="run-test-worker-1",
            workflow_id="default",
            workflow_updated_at=utc_now_iso(),
            status="queued",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            graph=self.graph,
            batches=[
                RunBatchState(
                    index=0,
                    status="pending",
                    node_ids=["q1"],
                )
            ],
            nodes={
                "q1": RunNodeState(
                    node_id="q1",
                    module_type="query_input",
                    batch_index=0,
                    status="pending",
                )
            },
        )

    def test_runtime_services_initialization(self) -> None:
        with patch("backend.storage.db_manager.DatabaseManager.is_connected", return_value=True), \
             patch("backend.storage.db_manager.DatabaseManager.ensure_schema", return_value=True):
            services = runtime_services()
            self.assertIsNotNone(services.module_registry)
            self.assertIsNotNone(services.workflow_executor)
            self.assertIsNotNone(services.run_store)
            self.assertTrue(services.module_registry.has("query_input"))
            self.assertTrue(services.module_registry.has("decomposer"))

    def test_compile_task_plan_from_run(self) -> None:
        with patch("backend.storage.db_manager.DatabaseManager.is_connected", return_value=True), \
             patch("backend.storage.db_manager.DatabaseManager.ensure_schema", return_value=True):
            services = runtime_services()
            plan = compile_task_plan(self.run, services.module_registry)
            self.assertEqual(len(plan), 1)
            self.assertIsInstance(plan[0], CompiledTaskNode)
            self.assertEqual(plan[0].node_id, "q1")
            self.assertEqual(plan[0].module_type, "query_input")

    def test_execute_with_policy_success(self) -> None:
        services = MagicMock()
        execute_with_policy(
            services=services,
            run_id="run-test-worker-1",
            node_id="q1",
            retries=2,
            retry_delay_seconds=0.0,
            timeout_seconds=5.0,
        )
        services.workflow_executor.execute_scheduled_node.assert_called_once_with(
            "run-test-worker-1", "q1"
        )

    def test_run_one_returns_none_when_queue_empty(self) -> None:
        mock_services = MagicMock()
        mock_services.db_manager.claim_next_workflow_run.return_value = None
        with patch("backend.engine.worker.main.runtime_services", return_value=mock_services):
            result = run_one("test-queue", "worker-1")
            self.assertIsNone(result)
