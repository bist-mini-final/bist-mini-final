import unittest

from backend.bi.fast_rag_adapter import FastRagPipelineAdapter
from backend.bi.tests.test_rag_adapter import retrieval_request


class RecordingRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    def execute(self, module_type: str, input_payload: dict, config: dict) -> dict:
        self.calls.append((module_type, input_payload, config))
        if module_type == "decomposer":
            return {
                "query_context": input_payload["query_context"],
                "subqueries": ["Revenue FY2025"],
            }
        if module_type == "embedder":
            return {
                "query_context": input_payload["query_context"],
                "items": {"Revenue FY2025": [1.0, 0.0]},
            }
        if module_type == "pgvector_retriever":
            return {
                "query_context": input_payload["query_input"]["query_context"],
                "document_context": {
                    "file_name": input_payload["index_input"]["file_name"],
                    "workbook_hash": input_payload["index_input"]["workbook_hash"],
                },
                "items": [
                    {
                        "rank": 1,
                        "cell_id": "income:B12",
                        "score": 0.99,
                        "text": "FY2025 Revenue 1,234.5",
                        "matched_subquery": "Revenue FY2025",
                    }
                ],
            }
        raise AssertionError(f"unexpected module call: {module_type}")


class RecordingCellStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fetch_cells_by_metadata(self, **kwargs) -> list[dict]:
        self.calls.append(kwargs)
        return [
            {
                "cell_id": "income:B12",
                "sheet_name": "Income Statement",
                "cell_coord": "B12",
                "source_text": "FY2025 Revenue 1,234.5",
            }
        ]


class FastRagPipelineAdapterTests(unittest.TestCase):
    def test_retrieves_only_ranked_cells_without_loading_collection(self) -> None:
        # Given: the BI adapter is wired to the existing registry and direct cell store.
        registry = RecordingRegistry()
        cell_store = RecordingCellStore()
        adapter = FastRagPipelineAdapter(registry, cell_store)

        # When: one BI metric question is retrieved from an indexed workbook.
        result = adapter.retrieve(retrieval_request())

        # Then: only the fast search modules run and only ranked evidence is fetched.
        self.assertEqual(
            [module_type for module_type, _, _ in registry.calls],
            ["decomposer", "embedder", "pgvector_retriever"],
        )
        self.assertNotIn(
            "pgvector_collection_loader",
            [module_type for module_type, _, _ in registry.calls],
        )
        self.assertEqual(
            cell_store.calls,
            [
                {
                    "cell_identifiers": ["income:B12"],
                    "workbook_hash": "a" * 64,
                    "collection_name": "index-1",
                    "limit": 100,
                }
            ],
        )
        self.assertEqual(result.cells[0].cell_id, "income:B12")
        self.assertIn("income:B12", result.context_blocks[0])

    def test_repeated_questions_never_materialize_full_index_documents(self) -> None:
        # Given: two questions target the same already indexed collection.
        registry = RecordingRegistry()
        adapter = FastRagPipelineAdapter(registry, RecordingCellStore())

        # When: both questions execute through the BI retrieval port.
        adapter.retrieve(retrieval_request())
        adapter.retrieve(retrieval_request())

        # Then: neither execution invokes a loader or sends document_input payloads.
        self.assertEqual(
            [call[0] for call in registry.calls].count("pgvector_retriever"),
            2,
        )
        self.assertFalse(
            any(
                "document_input" in input_payload
                for _, input_payload, _ in registry.calls
            )
        )


if __name__ == "__main__":
    unittest.main()
