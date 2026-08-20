import time
import unittest
from threading import Event
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.benchmark_routes import create_benchmark_router


class BenchmarkJobControlTests(unittest.TestCase):
    def test_job_pauses_between_runs_and_resumes(self) -> None:
        active = Event()
        finish_current = Event()

        def fake_execute(request, _store, _executor, on_progress, await_permission):
            on_progress({
                "event": "running",
                "completed": 0,
                "total": 2,
                "case_index": 0,
                "case_id": "q",
                "question": "question",
                "workflow_id": "one",
                "run_id": "run-one",
            })
            active.set()
            finish_current.wait(timeout=2)
            on_progress({
                "event": "completed",
                "completed": 1,
                "total": 2,
                "case_index": 0,
                "case_id": "q",
                "question": "question",
                "workflow_id": "one",
                "run_id": None,
                "error": None,
            })
            await_permission()
            return {
                "execution_mode": "sequential_isolated",
                "execution_scope": request.execution_scope,
                "use_cache": False,
                "summary": [],
                "results": [],
            }

        app = FastAPI()
        app.include_router(create_benchmark_router(None, None), prefix="/api")
        with patch("backend.api.benchmark_routes._execute_comparison", side_effect=fake_execute):
            with TestClient(app) as client:
                started = client.post("/api/benchmarks/jobs", json={
                    "workflow_ids": ["one", "two"],
                    "cases": [{"id": "q", "question": "question"}],
                    "execution_scope": "pre_retrieval",
                })
                self.assertEqual(started.status_code, 200)
                job_id = started.json()["id"]
                self.assertTrue(active.wait(timeout=2))

                paused = client.post(f"/api/benchmarks/jobs/{job_id}/pause")
                self.assertEqual(paused.status_code, 200)
                self.assertEqual(paused.json()["status"], "pausing")
                finish_current.set()

                status = None
                for _ in range(40):
                    status = client.get(f"/api/benchmarks/jobs/{job_id}").json()["status"]
                    if status == "paused":
                        break
                    time.sleep(0.025)
                self.assertEqual(status, "paused")

                resumed = client.post(f"/api/benchmarks/jobs/{job_id}/resume")
                self.assertEqual(resumed.status_code, 200)
                for _ in range(40):
                    status = client.get(f"/api/benchmarks/jobs/{job_id}").json()["status"]
                    if status == "completed":
                        break
                    time.sleep(0.025)
                self.assertEqual(status, "completed")


if __name__ == "__main__":
    unittest.main()
