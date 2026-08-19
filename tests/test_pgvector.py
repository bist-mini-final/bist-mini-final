import unittest
from backend.storage.pgvector_store import PgVectorStore


class FakeEmbeddingEncoder:
    def __init__(self, dimension: int = 4) -> None:
        self.dimension = dimension

    def encode(self, texts):
        return [
            [1.0 if "Gross" in t else 0.0 for _ in range(self.dimension)]
            for t in texts
        ]


class PgVectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = PgVectorStore()
        if not self.store.is_connected():
            self.skipTest("pgvector database is not accessible")
        self.encoder = FakeEmbeddingEncoder(dimension=4)

    def test_db_info(self):
        info = self.store.get_db_info()
        self.assertTrue(info["connected"])
        self.assertEqual(info["port"], 5432)
        self.assertIn("0.8", info["pgvector_version"])

    def test_put_search_delete_with_langchain(self):
        index_id = "test_langchain_idx_999"
        meta = {
            "file_name": "TestFinancial.xlsx",
            "workbook_hash": "hash_abc",
            "model": "text-embedding-3-large",
            "dimension": 4,
            "items": [
                {
                    "cell_id": "c1",
                    "sheet_name": "IS",
                    "cell_coord": "B2",
                    "text": "Gross Profit in 2024 is 500M",
                    "row_header": ["Gross Profit"],
                    "column_header": ["2024"],
                    "cell_value": "500M",
                },
                {
                    "cell_id": "c2",
                    "sheet_name": "IS",
                    "cell_coord": "B3",
                    "text": "Operating Expense in 2024 is 120M",
                    "row_header": ["Operating Expense"],
                    "column_header": ["2024"],
                    "cell_value": "120M",
                },
            ],
        }

        # 1. Put documents into LangChain PGVector
        self.store.put(index_id, None, meta, embedding_encoder=self.encoder)

        # 2. Search using query text
        hits = self.store.search(
            index_id,
            query_text="Gross Profit",
            embedding_encoder=self.encoder,
            limit=2,
        )
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0][1]["cell_id"], "c1")
        self.assertEqual(hits[0][1]["sheet_name"], "IS")

        direct_cells = self.store.fetch_cells_by_metadata(
            ["B2"],
            collection_name=index_id,
        )
        self.assertEqual(len(direct_cells), 1)
        self.assertEqual(direct_cells[0]["cell_id"], "c1")

        # 3. Get Detail
        detail = self.store.get_index_detail(index_id, limit=5)
        self.assertEqual(detail["index_id"], index_id)
        self.assertEqual(detail["document_count"], 2)

        # 4. Delete
        deleted = self.store.delete(index_id)
        self.assertTrue(deleted)


if __name__ == "__main__":
    unittest.main()
