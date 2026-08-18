import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.api.data_source_routes import create_data_source_router
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
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.processed_dir = self.root / "processed"
        self.vector_index_dir = self.root / "vector_db"
        self.embedding_artifact_dir = self.root / "artifacts"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.vector_index_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_artifact_dir.mkdir(parents=True, exist_ok=True)

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
        if self.pg_store.is_connected():
            for idx in self.pg_store.list_indexes():
                self.pg_store.delete(idx["index_id"])

        self.encoder = FakeEmbeddingEncoder(dimension=8)
        self.app = FastAPI()
        self.app.include_router(
            create_data_source_router(
                processed_dir=self.processed_dir,
                vector_index_dir=self.vector_index_dir,
                embedding_artifact_dir=self.embedding_artifact_dir,
                embedding_encoder=self.encoder,
                pgvector_store=self.pg_store,
            ),
            prefix="/api",
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        if hasattr(self, "pg_store") and self.pg_store.is_connected():
            for idx in self.pg_store.list_indexes():
                self.pg_store.delete(idx["index_id"])
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

    def test_upload_and_delete_file(self):
        file_content = b"fake-parquet-content"
        response = self.client.post(
            "/api/data-sources/files/upload",
            files={"file": ("uploaded_data.parquet", file_content, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.processed_dir / "uploaded_data.parquet").exists())

        # Delete it
        del_resp = self.client.delete("/api/data-sources/files/uploaded_data.parquet")
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse((self.processed_dir / "uploaded_data.parquet").exists())

    def test_ingest_excel_and_search(self):
        # Ingest the test workbook
        ingest_resp = self.client.post(
            "/api/data-sources/ingest",
            json={
                "file_name": "Test_Workbook.xlsx",
                "model": "text-embedding-3-large",
                "variant_mode": "header_only",
                "sheet_names": ["KeyStats"],
                "batch_size": 16,
            },
        )
        self.assertEqual(ingest_resp.status_code, 200)
        ingest_data = ingest_resp.json()
        self.assertEqual(ingest_data["status"], "success")
        index_id = ingest_data["index"]["index_id"]
        self.assertIsNotNone(index_id)

        # List indexes
        list_resp = self.client.get("/api/data-sources/indexes")
        self.assertEqual(list_resp.status_code, 200)
        indexes_data = list_resp.json()
        self.assertEqual(indexes_data["total"], 1)
        self.assertEqual(indexes_data["indexes"][0]["index_id"], index_id)

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
        self.assertEqual(list_after["total"], 0)


if __name__ == "__main__":
    unittest.main()
