from __future__ import annotations

import importlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.benchmark.application import BenchmarkApplicationService
from backend.domains.benchmark.application.ports import BenchmarkSetDocument
from backend.domains.benchmark.infrastructure.postgres import BENCHMARK_SCHEMA_SQL
from backend.domains.benchmark.presentation import create_benchmark_router
from backend.domains.workflow.domain.models import WorkflowSaveRequest
from backend.domains.workflow.infrastructure.job_catalog import canonical_workflow
from backend.domains.workflow.infrastructure.persistence import WorkflowStore
from jobs import BENCHMARK_JOB


class BenchmarkKubernetesContractTests(unittest.TestCase):
    def test_benchmark_job_uses_its_postgresql_kubernetes_queue(self) -> None:
        self.assertEqual(BENCHMARK_JOB.queue_name, "benchmark")
        entrypoint = BENCHMARK_JOB.worker_entrypoint
        self.assertIsNotNone(entrypoint)
        assert entrypoint is not None
        module_name, function_name = entrypoint.split(":", 1)
        function = getattr(importlib.import_module(module_name), function_name)
        self.assertTrue(callable(function))

    def test_benchmark_state_is_durable(self) -> None:
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS benchmark_jobs",
            BENCHMARK_SCHEMA_SQL,
        )
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS benchmark_result_rows",
            BENCHMARK_SCHEMA_SQL,
        )
        self.assertIn("result_payload JSONB", BENCHMARK_SCHEMA_SQL)
        self.assertIn("heartbeat_at TIMESTAMPTZ", BENCHMARK_SCHEMA_SQL)

    def test_api_only_enqueues_a_durable_benchmark_job(self) -> None:
        class RecordingStore:
            def __init__(self) -> None:
                self.enqueued: list[str] = []

            def enqueue(
                self,
                job_id: str,
                _request: dict[str, object],
                _total: int,
                _created_at: datetime,
            ) -> dict[str, object]:
                self.enqueued.append(job_id)
                return {"id": job_id}

        store = RecordingStore()

        class EmptyBenchmarkSets:
            def list_documents(self) -> tuple[BenchmarkSetDocument, ...]:
                return ()

        database = SimpleNamespace(database_url="postgresql://contract")
        run_store = SimpleNamespace(db_manager=database)
        with tempfile.TemporaryDirectory() as directory:
            workflow_store = WorkflowStore(Path(directory))
            rag_workflow = canonical_workflow("rag_query")
            assert rag_workflow is not None
            workflow_store.save(
                "rag_query_variant",
                WorkflowSaveRequest(
                    name="RAG query variant",
                    graph=rag_workflow.graph,
                ),
            )
            service = BenchmarkApplicationService(
                store=store,  # type: ignore[arg-type]
                workflow_store=workflow_store,
                run_store=run_store,  # type: ignore[arg-type]
                workflow_execution=SimpleNamespace(),  # type: ignore[arg-type]
                benchmark_sets=EmptyBenchmarkSets(),
                queue_available=True,
            )
            app = FastAPI()
            app.include_router(create_benchmark_router(service))
            response = TestClient(app).post(
                "/benchmarks/jobs",
                json={
                    "workflow_ids": ["rag_query", "rag_query_variant"],
                    "cases": [{"id": "case-1", "question": "test"}],
                    "execution_scope": "pre_retrieval",
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(store.enqueued, [response.json()["id"]])


if __name__ == "__main__":
    unittest.main()
