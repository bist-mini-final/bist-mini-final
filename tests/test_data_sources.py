import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.api.data_source_routes import create_data_source_router
from backend.core.settings import PGVECTOR_URL, WORKFLOW_DIR
from modules.common.base_module import ModuleExecutionError
from backend.engine.runtime.registry import ModuleRegistry
from backend.storage.spreadsheets.ingestion import search_vector_index
from backend.storage.answer_cache import AnswerCacheRepository
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.vector_index import VectorIndexStore
from backend.engine.workflows import (
    InteractiveWorkflowDispatcher,
    ResultCache,
    RunStore,
    WorkflowExecutor,
    WorkflowStore,
)


class NoApiCompletionClient:
    api_key = None


class FakeEmbeddingEncoder:
    def __init__(self, dimension: int = 8) -> None:
        self.dimension = dimension

    def encode(self, texts):
        return [
            [float((i + hash(text)) % 10) / 10.0 for i in range(self.dimension)]
            for text in texts
        ]


class DataSourceApiTests(unittest.TestCase):
    def setUp(self):
        """
        Prepare isolated test fixtures, sample spreadsheet data, storage clients, and a FastAPI test client.
        """
        self.test_id = uuid4().hex[:8]
        self.sample_filename = f"Test_Workbook_{self.test_id}.xlsx"
        self.upload_filename = f"uploaded_data_{self.test_id}.parquet"

        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.processed_dir = self.root / "processed"
        self.vector_index_dir = self.root / "vector_db"
        self.embedding_artifact_dir = self.root / "artifacts"
        self.spreadsheet_artifact_dir = self.root / "spreadsheet_artifacts"
        self.run_dir = self.root / "runs"
        self.cache_dir = self.root / "cache"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.vector_index_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_artifact_dir.mkdir(parents=True, exist_ok=True)
        self.spreadsheet_artifact_dir.mkdir(parents=True, exist_ok=True)

        # Create a sample workbook
        self.sample_file = self.processed_dir / self.sample_filename
        wb = Workbook()
        ws = wb.active
        ws.title = "KeyStats"
        ws.append(["Metric", "2023", "2024"])
        ws.append(["Revenue", "100M", "120M"])
        ws.append(["Net Income", "20M", "25M"])
        wb.save(self.sample_file)

        test_db_url = os.getenv(
            "TEST_PGVECTOR_URL",
            os.getenv("TEST_DATABASE_URL", PGVECTOR_URL),
        )
        self.pg_store = PgVectorStore(test_db_url)
        self.db_mgr = DatabaseManager(test_db_url)
        if not self.pg_store.is_connected() or not self.db_mgr.is_connected():
            self.temp_dir.cleanup()
            self.skipTest("pgvector database is not accessible")
        self.db_mgr.ensure_schema()
        info = self.pg_store.get_db_info()
        if info.get("pgvector_version") == "not installed":
            self.temp_dir.cleanup()
            self.skipTest("pgvector extension is not installed in PostgreSQL")
        self.clean_test_indexes(self.test_id)

        self.encoder = FakeEmbeddingEncoder(dimension=8)
        self.embedding_store = EmbeddingArtifactStore(self.embedding_artifact_dir)
        self.vector_store = VectorIndexStore(self.vector_index_dir)
        self.module_registry = ModuleRegistry(
            AnswerCacheRepository(),
            completion_client=NoApiCompletionClient(),
            embedding_encoder=self.encoder,
            embedding_artifact_store=self.embedding_store,
            vector_index_store=self.vector_store,
            pgvector_store=self.pg_store,
            db_manager=self.db_mgr,
            processed_dir=self.processed_dir,
            spreadsheet_artifact_dir=self.spreadsheet_artifact_dir,
        )
        self.workflow_store = WorkflowStore(WORKFLOW_DIR)
        self.run_store = RunStore(self.run_dir)
        self.workflow_executor = WorkflowExecutor(
            self.module_registry,
            self.run_store,
            ResultCache(self.cache_dir),
        )
        self.workflow_dispatcher = InteractiveWorkflowDispatcher(
            self.workflow_executor,
            self.run_store,
        )
        self.app = FastAPI()
        self.app.include_router(
            create_data_source_router(
                processed_dir=self.processed_dir,
                vector_index_dir=self.vector_index_dir,
                embedding_artifact_dir=self.embedding_artifact_dir,
                spreadsheet_artifact_dir=self.spreadsheet_artifact_dir,
                run_dir=self.run_dir,
                cache_dir=self.cache_dir,
                embedding_encoder=self.encoder,
                pgvector_store=self.pg_store,
                module_registry=self.module_registry,
                workflow_store=self.workflow_store,
                run_store=self.run_store,
                workflow_executor=self.workflow_executor,
                workflow_dispatcher=self.workflow_dispatcher,
            ),
            prefix="/api",
        )
        self.client = TestClient(self.app)

    def clean_test_indexes(self, test_id: Optional[str] = None):
        """Remove test-created vector indexes and source-file records from connected stores."""
        target_id = test_id or getattr(self, "test_id", None)
        target_files = [
            getattr(self, "sample_filename", f"Test_Workbook_{target_id}.xlsx" if target_id else "Test_Workbook.xlsx"),
            getattr(self, "upload_filename", f"uploaded_data_{target_id}.parquet" if target_id else "uploaded_data.parquet"),
        ]
        if hasattr(self, "pg_store") and self.pg_store.is_connected():
            for idx in self.pg_store.list_indexes():
                file_name = idx.get("file_name", "")
                index_id = idx.get("index_id", "")
                if target_id and (target_id in file_name or target_id in index_id):
                    self.pg_store.delete(index_id)
                elif not target_id and ("Test_Workbook" in file_name or index_id.startswith("test_")):
                    self.pg_store.delete(index_id)
        if hasattr(self, "db_mgr") and self.db_mgr.is_connected():
            with self.db_mgr._raw_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM source_files 
                        WHERE file_name = ANY(%s);
                        """,
                        (target_files,),
                    )
                conn.commit()

    def tearDown(self):
        """
        Release resources created during the test and cancel any queued or running workflows.
        """
        if hasattr(self, "run_store") and hasattr(self, "workflow_dispatcher"):
            for run in self.run_store.list():
                if run.status in {"queued", "running"}:
                    self.workflow_dispatcher.cancel(run.id)
        if hasattr(self, "workflow_dispatcher"):
            self.workflow_dispatcher.shutdown(wait=True)
        if hasattr(self, "client"):
            self.client.close()
        self.clean_test_indexes(getattr(self, "test_id", None))
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    def _await_job(self, run_id: str, timeout: float = 30.0) -> dict:
        """
        Wait for an ingestion job to reach a terminal status and return its final payload.
        
        Parameters:
        	run_id (str): Identifier of the ingestion job to monitor.
        	timeout (float): Maximum number of seconds to wait for completion.
        
        Returns:
        	dict: The job payload with a completed or failed status.
        
        Raises:
        	AssertionError: If a status request fails or the job does not finish within the timeout.
        """
        deadline = time.monotonic() + timeout
        response = self.client.get(f"/api/data-sources/ingestion-jobs/{run_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        while payload["status"] not in {"completed", "failed"}:
            if time.monotonic() >= deadline:
                self.fail(
                    f"ingestion job {run_id} did not finish in {timeout}s "
                    f"(last status={payload['status']})"
                )
            time.sleep(0.05)
            response = self.client.get(f"/api/data-sources/ingestion-jobs/{run_id}")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
        return payload

    def test_list_files(self):
        response = self.client.get("/api/data-sources/files")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["files"][0]["file_name"], self.sample_filename)
        self.assertIn("KeyStats", data["files"][0]["sheet_names"])

    def test_preview_file(self):
        response = self.client.get(f"/api/data-sources/files/{self.sample_filename}/preview")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sheet_name"], "KeyStats")
        self.assertGreater(len(data["preview_rows"]), 0)

    def test_cancel_unknown_ingestion_job_returns_not_found(self):
        response = self.client.post(
            "/api/data-sources/ingestion-jobs/run-missing/cancel"
        )

        self.assertEqual(response.status_code, 404)

    def test_delete_unknown_ingestion_job_returns_not_found(self):
        response = self.client.delete(
            "/api/data-sources/ingestion-jobs/run-missing"
        )

        self.assertEqual(response.status_code, 404)

    def test_upload_download_and_delete_file(self):
        file_content = b"fake-parquet-content-12345"
        response = self.client.post(
            "/api/data-sources/files/upload",
            files={"file": (self.upload_filename, file_content, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.processed_dir / self.upload_filename).exists())

        # Test download endpoint from DB BLOB
        dl_resp = self.client.get(f"/api/data-sources/files/{self.upload_filename}/download")
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(dl_resp.content, file_content)

        # Delete it
        del_resp = self.client.delete(f"/api/data-sources/files/{self.upload_filename}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse((self.processed_dir / self.upload_filename).exists())

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""})
    def test_ingest_excel_and_search(self):
        # Queue and poll the canonical workflow job.
        ingest_resp = self.client.post(
            "/api/data-sources/ingestion-jobs",
            json={
                "file_name": self.sample_filename,
                "model": "text-embedding-3-large",
                "variant_mode": "header_only",
                "structure_mode": "exhaustive",
                "sheet_names": ["KeyStats"],
                "batch_size": 16,
            },
        )
        self.assertEqual(ingest_resp.status_code, 202)
        ingest_data = ingest_resp.json()
        run_id = ingest_data["job_id"]
        ingest_data = self._await_job(run_id)

        self.assertEqual(
            ingest_data["status"],
            "completed",
            ingest_data.get("error"),
        )
        index_id = ingest_data["index"]["index_id"]
        self.assertIsNotNone(index_id)

        # List indexes
        list_resp = self.client.get("/api/data-sources/indexes")
        self.assertEqual(list_resp.status_code, 200)
        indexes_data = list_resp.json()
        found_ids = [idx["index_id"] for idx in indexes_data["indexes"]]
        self.assertIn(index_id, found_ids)

        # Get index detail
        detail_resp = self.client.get(f"/api/data-sources/indexes/{index_id}")
        self.assertEqual(detail_resp.status_code, 200)
        detail_data = detail_resp.json()
        self.assertEqual(detail_data["index_id"], index_id)
        self.assertGreater(len(detail_data["sample_items"]), 0)
        self.assertIn("duration_seconds", detail_data)
        self.assertIn("total_tokens", detail_data)
        self.assertIn("estimated_cost_usd", detail_data)

        # Test search
        search_resp = self.client.post(
            f"/api/data-sources/indexes/{index_id}/search",
            json={"query": "Revenue 2024", "limit": 3},
        )
        self.assertEqual(search_resp.status_code, 200)
        search_data = search_resp.json()
        self.assertGreater(len(search_data["results"]), 0)

        # Delete index
        delete_resp = self.client.delete(f"/api/data-sources/indexes/{index_id}")
        self.assertEqual(delete_resp.status_code, 200)

        # Confirm deleted
        list_after = self.client.get("/api/data-sources/indexes").json()
        deleted_ids = [idx["index_id"] for idx in list_after["indexes"]]
        self.assertNotIn(index_id, deleted_ids)

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""})
    def test_background_ingestion_job_is_persisted_and_pollable(self):
        start_response = self.client.post(
            "/api/data-sources/ingestion-jobs",
            json={
                "file_name": self.sample_filename,
                "model": "text-embedding-3-large",
                "variant_mode": "header_only",
                "structure_mode": "exhaustive",
                "sheet_names": ["KeyStats"],
                "batch_size": 16,
            },
        )
        self.assertEqual(start_response.status_code, 202)
        started = start_response.json()
        self.assertEqual(started["workflow_id"], "indexing_pgvector_exhaustive")
        self.assertIn(started["status"], {"queued", "running", "completed"})
        run_id = started["job_id"]
        self.assertTrue((self.run_dir / f"{run_id}.json").is_file())

        current = self._await_job(run_id)

        self.assertEqual(current["status"], "completed", current.get("error"))
        self.assertIsNotNone(current["index"])
        self.assertGreater(current["index"]["document_count"], 0)
        status_by_module = {
            node["module_type"]: current["run"]["nodes"][node["id"]]["status"]
            for node in current["run"]["graph"]["nodes"]
        }
        for module_type in (
            "company_entity_extractor",
            "sheet_metadata_persistence",
            "index_company_persistence",
        ):
            self.assertEqual(status_by_module[module_type], "succeeded")
        self.assertEqual(current["index"]["company_name"], f"Test Workbook {self.test_id}")
        history_response = self.client.get(
            f"/api/data-sources/ingestion-jobs/by-index/{current['index']['index_id']}"
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json()["job_id"], run_id)
        resume_response = self.client.post(
            f"/api/data-sources/ingestion-jobs/{run_id}/resume"
        )
        self.assertEqual(resume_response.status_code, 409)
        list_response = self.client.get(
            "/api/data-sources/ingestion-jobs",
            params={"file_name": self.sample_filename},
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(run_id, [job["job_id"] for job in list_response.json()["jobs"]])

        delete_response = self.client.delete(
            f"/api/data-sources/ingestion-jobs/{run_id}"
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["source_file_preserved"])
        self.assertTrue(self.sample_file.is_file())
        self.assertEqual(
            self.client.get(f"/api/data-sources/ingestion-jobs/{run_id}").status_code,
            404,
        )

    @patch("backend.api.data_source_routes.PgVectorStore.get_db_info")
    def test_db_connect_valid_host(self, mock_get_db_info):
        mock_get_db_info.return_value = {
            "connected": True,
            "host": "localhost",
            "port": 5432,
            "database": "rag_flow",
            "postgres_version": "16",
            "pgvector_version": "0.8.6",
            "framework": "LangChain",
            "total_indexes": 1,
            "total_chunks": 10,
        }
        response = self.client.post(
            "/api/data-sources/db-connect",
            json={"database_url": "postgresql://postgres:postgres@localhost:5432/rag_flow"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["connected"])
        self.assertEqual(data["host"], "localhost")

    def test_db_connect_disallowed_host(self):
        response = self.client.post(
            "/api/data-sources/db-connect",
            json={"database_url": "postgresql://user:pass@evil-internal-host.com:5432/db"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("허용되지 않은 데이터베이스 호스트", response.json()["detail"])

    def test_db_connect_invalid_scheme(self):
        response = self.client.post(
            "/api/data-sources/db-connect",
            json={"database_url": "http://localhost:5432/rag_flow"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("PostgreSQL 데이터베이스 URL만 지원", response.json()["detail"])

    @patch("backend.api.data_source_routes.PgVectorStore.get_db_info")
    def test_db_connect_sanitizes_failure_response(self, mock_get_db_info):
        mock_get_db_info.return_value = {
            "connected": False,
            "host": "127.0.0.1",
            "port": 5432,
            "database": "rag_flow",
            "framework": "LangChain",
            "error": "psycopg2.OperationalError: password authentication failed for user 'secret_user'",
            "total_indexes": 0,
            "total_chunks": 0,
        }
        response = self.client.post(
            "/api/data-sources/db-connect",
            json={"database_url": "postgresql://secret_user:secret_pass@127.0.0.1:5432/rag_flow"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["connected"])
        self.assertEqual(data["error"], "데이터베이스 연결에 실패했습니다.")
        self.assertNotIn("secret_user", data["error"])

    @patch("backend.api.data_source_routes.PgVectorStore.get_db_info", side_effect=RuntimeError("internal crash"))
    def test_db_connect_sanitizes_exception(self, _mock):
        response = self.client.post(
            "/api/data-sources/db-connect",
            json={"database_url": "postgresql://postgres:postgres@localhost:5432/rag_flow"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["connected"])
        self.assertEqual(data["error"], "데이터베이스 연결에 실패했습니다.")
        self.assertNotIn("internal crash", str(data))

    @patch("backend.storage.pgvector_store.PgVectorStore.get_index_detail", side_effect=Exception("collection not found"))
    @patch("backend.storage.pgvector_store.PgVectorStore.is_connected", return_value=True)
    def test_search_vector_index_raises_when_detail_fails(self, _mock_conn, _mock_detail):
        with self.assertRaises(ModuleExecutionError) as ctx:
            search_vector_index(
                "invalid_index_id",
                "test query",
                pgvector_store=self.pg_store,
            )
        self.assertIn("모델 정보를 확인할 수 없습니다", str(ctx.exception))

    @patch("backend.storage.pgvector_store.PgVectorStore.get_index_detail", return_value={"model": ""})
    @patch("backend.storage.pgvector_store.PgVectorStore.is_connected", return_value=True)
    def test_search_vector_index_raises_when_model_empty(self, _mock_conn, _mock_detail):
        with self.assertRaises(ModuleExecutionError) as ctx:
            search_vector_index(
                "no_model_index_id",
                "test query",
                pgvector_store=self.pg_store,
            )
        self.assertIn("임베딩 모델명을 확인할 수 없습니다", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
