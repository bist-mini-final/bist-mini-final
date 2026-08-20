import unittest
from urllib.parse import urlparse
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from backend.storage.pgvector_store import PgVectorStore, PgVectorStoreError


class FakeEmbeddingEncoder:
    def __init__(self, dimension: int = 4) -> None:
        self.dimension = dimension

    def encode(self, texts):
        return [
            [1.0 if "Gross" in t else 0.0 for _ in range(self.dimension)]
            for t in texts
        ]


class CapturingCursor:
    def __init__(self) -> None:
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params):
        self.executions.append((" ".join(query.split()), params))

    def fetchall(self):
        return []


class CapturingConnection:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class PgVectorMetadataQueryTests(unittest.TestCase):
    def test_qualified_cell_reference_pairs_sheet_and_coordinate(self):
        cursor = CapturingCursor()
        store = object.__new__(PgVectorStore)
        store._raw_connection = lambda: CapturingConnection(cursor)

        self.assertEqual(
            store.fetch_cells_by_metadata(
                ["O17"],
                workbook_hash="workbook-hash",
                cell_references=[
                    {
                        "sheet_name": "Income_Statement",
                        "cell_coord": "O17",
                    }
                ],
            ),
            [],
        )

        query, params = cursor.executions[-1]
        self.assertIn("UPPER(cmetadata->>'sheet_name') = reference.sheet_name", query)
        self.assertIn("UPPER(cmetadata->>'cell_coord') = reference.cell_coord", query)
        self.assertIn("ROW_NUMBER() OVER", query)
        self.assertIn("WHERE cell_rank = 1", query)
        self.assertIn("ORDER BY UPPER(sheet_name), UPPER(cell_coord), id LIMIT %s", query)
        self.assertEqual(params[:2], (["INCOME_STATEMENT"], ["O17"]))
        self.assertEqual(params[2], "workbook-hash")

    def test_cell_items_to_langchain_documents_preserves_variant(self):
        from backend.spreadsheets.langchain_document import cell_items_to_langchain_documents
        from backend.modules.cell_text_serializer import CellTextDocumentDTO

        dto = CellTextDocumentDTO(
            cell_id="cell-1",
            sheet_name="Summary",
            cell_coord="B2",
            row_header=["Total"],
            column_header=["2025"],
            cell_value="100",
            variant="header_with_value",
            text="Total 2025: 100",
        )
        docs = cell_items_to_langchain_documents([dto], file_name="test.xlsx")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].metadata["variant"], "header_with_value")
        self.assertEqual(docs[0].metadata["file_name"], "test.xlsx")

        dict_item = {
            "cell_id": "cell-2",
            "sheet_name": "Summary",
            "cell_coord": "B3",
            "variant": "header_only",
            "text": "Total 2025",
        }
        docs_dict = cell_items_to_langchain_documents([dict_item])
        self.assertEqual(docs_dict[0].metadata["variant"], "header_only")
        self.assertEqual(docs_dict[0].id, "cell-2#0")

        docs_with_index = cell_items_to_langchain_documents([dto], file_name="test.xlsx", index_id="idx_123")
        self.assertEqual(docs_with_index[0].id, "idx_123:cell-1#0")

        docs_with_hash = cell_items_to_langchain_documents([dto], file_name="test.xlsx", workbook_hash="hash_abc")
        self.assertEqual(docs_with_hash[0].id, "hash_abc:cell-1#0")


class PgVectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = PgVectorStore()
        if not self.store.is_connected():
            self.skipTest("pgvector database is not accessible")
        self.encoder = FakeEmbeddingEncoder(dimension=4)

    def test_db_info(self):
        info = self.store.get_db_info()
        self.assertTrue(info["connected"])
        expected_port = urlparse(self.store.database_url).port or 5432
        self.assertEqual(info["port"], expected_port)
        self.assertIn("0.8", info["pgvector_version"])

    def test_put_search_delete_with_langchain(self):
        index_id = "test_langchain_idx_999"
        self.store.delete(index_id)
        self.addCleanup(self.store.delete, index_id)
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
                {
                    "cell_id": "c1",
                    "sheet_name": "IS",
                    "cell_coord": "B2",
                    "text": "ZZZ alternate Gross Profit serialization",
                    "row_header": ["Gross Profit alternate"],
                    "column_header": ["2024"],
                    "cell_value": "500M",
                },
                {
                    "cell_id": "c3",
                    "sheet_name": "BS",
                    "cell_coord": "B2",
                    "text": "Total Assets in 2024 is 900M",
                    "row_header": ["Total Assets"],
                    "column_header": ["2024"],
                    "cell_value": "900M",
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
            cell_references=[{"sheet_name": "IS", "cell_coord": "B2"}],
        )
        self.assertEqual(len(direct_cells), 1)
        self.assertEqual(direct_cells[0]["cell_id"], "c1")

        balance_sheet_cells = self.store.fetch_cells_by_metadata(
            ["B2"],
            collection_name=index_id,
            cell_references=[{"sheet_name": "BS", "cell_coord": "B2"}],
        )
        self.assertEqual(len(balance_sheet_cells), 1)
        self.assertEqual(balance_sheet_cells[0]["cell_id"], "c3")

        limited_cells = self.store.fetch_cells_by_metadata(
            ["B2", "B3"],
            collection_name=index_id,
            cell_references=[
                {"sheet_name": "IS", "cell_coord": "B2"},
                {"sheet_name": "IS", "cell_coord": "B3"},
            ],
            limit=2,
        )
        self.assertEqual(
            [(cell["sheet_name"], cell["cell_coord"]) for cell in limited_cells],
            [("IS", "B2"), ("IS", "B3")],
        )

        # 3. Get Detail
        detail = self.store.get_index_detail(index_id, limit=5)
        self.assertEqual(detail["index_id"], index_id)
        self.assertEqual(detail["document_count"], 4)

        # 4. Delete
        deleted = self.store.delete(index_id)
        self.assertTrue(deleted)

    @patch("backend.storage.pgvector_store.get_vector_store")
    def test_put_documents_propagates_delete_collection_failure(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.delete_collection.side_effect = RuntimeError("DB delete lock timeout")
        mock_get_store.return_value = mock_store

        test_docs = [Document(page_content="test", metadata={"cell_id": "c1"})]
        with self.assertRaises(PgVectorStoreError) as ctx:
            self.store.put_documents("test_index", test_docs)

        self.assertIn("삭제 실패", str(ctx.exception))
        self.assertIn("DB delete lock timeout", str(ctx.exception))
        mock_store.create_collection.assert_not_called()
        mock_store.add_documents.assert_not_called()

    @patch("backend.storage.pgvector_store.get_vector_store")
    def test_put_documents_propagates_create_collection_failure(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.delete_collection.return_value = None
        mock_store.create_collection.side_effect = RuntimeError("DB create collection error")
        mock_get_store.return_value = mock_store

        test_docs = [Document(page_content="test", metadata={"cell_id": "c1"})]
        with self.assertRaises(PgVectorStoreError) as ctx:
            self.store.put_documents("test_index", test_docs)

        self.assertIn("생성 실패", str(ctx.exception))
        self.assertIn("DB create collection error", str(ctx.exception))
        mock_store.add_documents.assert_not_called()

    @patch("backend.storage.pgvector_store.get_vector_store")
    def test_put_documents_raises_on_vector_count_mismatch(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.delete_collection.return_value = None
        mock_store.create_collection.return_value = None
        mock_get_store.return_value = mock_store

        test_docs = [
            Document(page_content="doc1", metadata={"cell_id": "c1"}),
            Document(page_content="doc2", metadata={"cell_id": "c2"}),
        ]
        # Provided 1 vector for 2 documents -> mismatch!
        vectors = [[0.1, 0.2, 0.3]]

        with self.assertRaises(PgVectorStoreError) as ctx:
            self.store.put_documents("test_index", test_docs, vectors=vectors)

        self.assertIn("사전 계산된 벡터 개수(1)가 문서 개수(2)와 일치하지 않습니다", str(ctx.exception))
        mock_store.add_documents.assert_not_called()
        mock_store.add_embeddings.assert_not_called()

    @patch("backend.storage.pgvector_store.get_vector_store")
    def test_put_documents_uses_precomputed_vectors_when_matching(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.delete_collection.return_value = None
        mock_store.create_collection.return_value = None
        mock_get_store.return_value = mock_store

        test_docs = [
            Document(page_content="doc1", metadata={"cell_id": "c1"}),
            Document(page_content="doc2", metadata={"cell_id": "c2"}),
        ]
        vectors = [[0.1, 0.2], [0.3, 0.4]]

        with patch.object(self.store, "_raw_connection") as mock_conn, \
             patch.object(self.store, "ensure_optimized_indexes"):
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            self.store.put_documents("test_index", test_docs, vectors=vectors)

        mock_store.add_embeddings.assert_called_once()
        mock_store.add_documents.assert_not_called()


if __name__ == "__main__":
    unittest.main()
