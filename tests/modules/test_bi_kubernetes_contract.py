from __future__ import annotations

import importlib
import unittest
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.features.bi.api_routes import create_bi_router
from backend.features.bi.api_services import BiApiServices
from backend.features.bi.database_schema import (
    BI_SCHEMA_LOCK_KEY,
    BI_SCHEMA_SQL,
    ensure_bi_schema,
)
from backend.features.bi.materialization_models import BiCompanyIndexEntry
from backend.features.bi.models import (
    BiCompany,
    BiMaterializationJob,
    BiMaterializationSource,
    CompanyId,
    IndexId,
)
from jobs import BI_MATERIALIZATION_JOB, BI_QUESTION_JOB


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 23, 12, tzinfo=UTC)


class RecordingBiStore:
    def __init__(self) -> None:
        self.enqueued: list[BiMaterializationJob] = []
        self.entries: tuple[BiCompanyIndexEntry, ...] = ()
        self.company: BiCompany | None = None
        self.deleted_dashboard_company_ids: list[CompanyId] = []

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

    async def list_companies_async(self) -> tuple[BiCompanyIndexEntry, ...]:
        return self.entries

    async def get_current_many_async(self, *_args: object) -> dict[object, object]:
        return {}

    async def get_latest_jobs_async(self, *_args: object) -> dict[object, object]:
        return {}

    async def get_company_async(self, *_args: object) -> BiCompany | None:
        return self.company

    async def delete_dashboard_snapshot_async(self, company_id: CompanyId) -> bool:
        self.deleted_dashboard_company_ids.append(company_id)
        return True


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

    def test_bi_schema_bootstrap_has_a_stable_cross_process_lock_key(self) -> None:
        self.assertEqual(BI_SCHEMA_LOCK_KEY, "bist:bi-schema:v1")

    def test_bi_schema_bootstrap_takes_lock_before_running_ddl(self) -> None:
        pooled = MagicMock()
        connection = pooled.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value

        with patch(
            "backend.features.bi.database_schema.get_pooled_raw_connection",
            return_value=pooled,
        ):
            ensure_bi_schema("postgresql://example")

        cursor.execute.assert_has_calls(
            [
                call(
                    "SELECT pg_advisory_xact_lock(hashtext(%s));",
                    (BI_SCHEMA_LOCK_KEY,),
                ),
                call(BI_SCHEMA_SQL),
            ]
        )
        connection.commit.assert_called_once_with()

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

    def test_candidate_api_exposes_snapshotless_index_without_changing_dashboard_filter(
        self,
    ) -> None:
        store = RecordingBiStore()
        store.entries = (
            BiCompanyIndexEntry(
                company=BiCompany(
                    company_id=CompanyId("amesoft"),
                    display_name="AmeSoft",
                ),
                source=BiMaterializationSource(
                    file_name="amesoft.xlsx",
                    workbook_hash="b" * 64,
                    index_id=IndexId("index-amesoft"),
                ),
            ),
        )
        services = BiApiServices(
            store=store,  # type: ignore[arg-type]
            materializations=store,  # type: ignore[arg-type]
            clock=FixedClock(),
            questions=UnusedQuestions(),  # type: ignore[arg-type]
        )
        app = FastAPI()
        app.include_router(create_bi_router(services))

        response = TestClient(app).get("/bi/materialization-candidates")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["candidates"][0]["company_id"], "amesoft")
        self.assertEqual(response.json()["candidates"][0]["reason"], "not_created")

    def test_dashboard_delete_keeps_the_source_company_available_for_recreation(self) -> None:
        store = RecordingBiStore()
        store.company = BiCompany(
            company_id=CompanyId("amesoft"),
            display_name="AmeSoft",
        )
        services = BiApiServices(
            store=store,  # type: ignore[arg-type]
            materializations=store,  # type: ignore[arg-type]
            clock=FixedClock(),
            questions=UnusedQuestions(),  # type: ignore[arg-type]
        )
        app = FastAPI()
        app.include_router(create_bi_router(services))

        response = TestClient(app).delete("/bi/companies/amesoft/dashboard")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(store.deleted_dashboard_company_ids, [CompanyId("amesoft")])
        self.assertEqual(response.content, b"")


if __name__ == "__main__":
    unittest.main()
