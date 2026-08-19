import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.api.data_source_routes import create_data_source_router
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.vector_index import VectorIndexStore


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
        self.sample_file = self.processed_dir / "Test_Workbook.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "KeyStats"
        ws.append(["Metric", "2023", "2024"])
        ws.append(["Revenue", "100M", "120M"])
        ws.append(["Net Income", "20M", "25M"])
        wb.save(self.sample_file)

        self.pg_store = PgVectorStore()
        self.db_mgr = DatabaseManager()
        self.clean_test_indexes()

        self.encoder = FakeEmbeddingEncoder(dimension=8)
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
            ),
            prefix="/api",
        )
        self.client = TestClient(self.app)

    def clean_test_indexes(self):
        if hasattr(self, "pg_store") and self.pg_store.is_connected():
            for idx in self.pg_store.list_indexes():
                if "Test_Workbook" in idx.get("file_name", "") or idx["index_id"].startswith("test_"):
                    self.pg_store.delete(idx["index_id"])
        if hasattr(self, "db_mgr") and self.db_mgr.is_connected():
            with self.db_mgr._raw_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM source_files 
                        WHERE file_name ILIKE '%Test_Workbook%' 
                           OR file_name ILIKE '%test_%' 
                           OR file_name = 'uploaded_data.parquet';
                    """)
                conn.commit()

    def tearDown(self):
        self.clean_test_indexes()
        self.temp_dir.cleanup()

    def test_list_files(self):
        response = self.client.get("/api/data-sources/files")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["files"][0]["file_name"], "Test_Workbook.xlsx")
        self.assertIn("KeyStats", data["files"][0]["sheet_names"])

    def test_preview_file(self):
        response = self.client.get("/api/data-sources/files/Test_Workbook.xlsx/preview")
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
            files={"file": ("uploaded_data.parquet", file_content, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.processed_dir / "uploaded_data.parquet").exists())

        # Test download endpoint from DB BLOB
        dl_resp = self.client.get("/api/data-sources/files/uploaded_data.parquet/download")
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(dl_resp.content, file_content)

        # Delete it
        del_resp = self.client.delete("/api/data-sources/files/uploaded_data.parquet")
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse((self.processed_dir / "uploaded_data.parquet").exists())

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""})
    def test_ingest_excel_and_search(self):
        # Queue and poll the canonical workflow job.
        ingest_resp = self.client.post(
            "/api/data-sources/ingestion-jobs",
            json={
                "file_name": "Test_Workbook.xlsx",
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
        deadline = time.monotonic() + 5
        while (
            ingest_data["status"] not in {"completed", "failed"}
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
            ingest_data = self.client.get(
                f"/api/data-sources/ingestion-jobs/{run_id}"
            ).json()

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
                "file_name": "Test_Workbook.xlsx",
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

        deadline = time.monotonic() + 5
        current = started
        while current["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.05)
            response = self.client.get(f"/api/data-sources/ingestion-jobs/{run_id}")
            self.assertEqual(response.status_code, 200)
            current = response.json()

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
        self.assertEqual(current["index"]["company_name"], "Test Workbook")
        history_response = self.client.get(
            f"/api/data-sources/ingestion-jobs/by-index/{current['index']['index_id']}"
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json()["job_id"], run_id)
        list_response = self.client.get(
            "/api/data-sources/ingestion-jobs",
            params={"file_name": "Test_Workbook.xlsx"},
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


if __name__ == "__main__":
    unittest.main()
