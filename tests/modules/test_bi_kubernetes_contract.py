from __future__ import annotations

import importlib
import unittest
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.features.bi.api_routes import create_bi_router
from backend.features.bi.api_services import BiApiServices
from backend.features.bi.database_schema import BI_SCHEMA_SQL
from backend.features.bi.models import BiMaterializationJob
from jobs import BI_MATERIALIZATION_JOB, BI_QUESTION_JOB


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 23, 12, tzinfo=UTC)


class RecordingBiStore:
    def __init__(self) -> None:
        self.enqueued: list[BiMaterializationJob] = []

    def find_latest_job(self, *_args: object) -> None:
        raise AssertionError("async API must not call sync find_latest_job")

    async def find_latest_job_async(self, *_args: object) -> None:
        return None

    def get_latest_job(self, *_args: object) -> None:
        return None

    def enqueue(self, _request: object, job: BiMaterializationJob) -> BiMaterializationJob:
        raise AssertionError("async API must not call sync enqueue")

    async def enqueue_async(
        self,
        _request: object,
        job: BiMaterializationJob,
    ) -> BiMaterializationJob:
        self.enqueued.append(job)
        return job

    def list_companies(self) -> tuple[()]:
        return ()


class UnusedQuestions:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"question service must not be called: {name}")


class BiKubernetesContractTests(unittest.TestCase):
    def test_materialization_job_points_to_kubernetes_worker_entrypoint(self) -> None:
        expected = (
            (BI_MATERIALIZATION_JOB, "bi-materialization"),
            (BI_QUESTION_JOB, "bi-question"),
        )
        for job, queue_name in expected:
            self.assertEqual(job.queue_name, queue_name)
            entrypoint = job.worker_entrypoint
            self.assertIsNotNone(entrypoint)
            assert entrypoint is not None
            module_name, function_name = entrypoint.split(":", 1)
            function = getattr(importlib.import_module(module_name), function_name)
            self.assertTrue(callable(function))

    def test_bi_schema_contains_all_durable_control_plane_tables(self) -> None:
        for table in (
            "bi_companies",
            "bi_materialization_jobs",
            "bi_dashboard_snapshots",
            "bi_questions",
            "bi_answers",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", BI_SCHEMA_SQL)

    def test_materialization_api_only_enqueues_and_returns_accepted(self) -> None:
        store = RecordingBiStore()
        services = BiApiServices(
            store=store,  # type: ignore[arg-type]
            materializations=store,  # type: ignore[arg-type]
            clock=FixedClock(),
            questions=UnusedQuestions(),  # type: ignore[arg-type]
        )
        app = FastAPI()
        app.include_router(create_bi_router(services))
        response = TestClient(app).post(
            "/bi/materializations",
            json={
                "company_id": "samsung-electronics",
                "display_name": "삼성전자",
                "source": {
                    "file_name": "samsung.xlsx",
                    "workbook_hash": "a" * 64,
                    "index_id": "index-samsung",
                },
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(store.enqueued), 1)
        self.assertEqual(store.enqueued[0].status.value, "queued")
        self.assertEqual(response.json()["job_id"], str(store.enqueued[0].job_id))


if __name__ == "__main__":
    unittest.main()
