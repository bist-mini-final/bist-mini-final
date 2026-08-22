import unittest

from backend.bi.rag_adapter import ExistingRagPipelineAdapter
from backend.bi.rag_modules import ExistingRagPipelineModules
from backend.bi.tests.test_rag_adapter import FakeRagModules, retrieval_request


class FakeModuleRegistry:
    def __init__(self) -> None:
        fixtures = FakeRagModules()
        query_context = retrieval_request().question
        from backend.bi.rag_pipeline_models import RagQueryContext

        query = RagQueryContext(question_id="QUERY-TEST", question_text=query_context)
        subqueries = fixtures.decompose(query)
        loaded = fixtures.load_index("index-1")
        embeddings = fixtures.embed(subqueries)
        bm25 = fixtures.retrieve_bm25(subqueries, loaded)
        dense = fixtures.retrieve_dense(embeddings, loaded)
        retrieval = fixtures.fuse(bm25, dense)
        context = fixtures.expand(retrieval, loaded)
        self.outputs = [
            ("decomposer", subqueries.model_dump(mode="json")),
            ("pgvector_collection_loader", loaded.model_dump(mode="json")),
            ("embedder", embeddings.model_dump(mode="json")),
            ("bm25_retriever", bm25.model_dump(mode="json")),
            ("pgvector_retriever", dense.model_dump(mode="json")),
            ("rrf_fusion", retrieval.model_dump(mode="json")),
            ("context", {"context_json": context.model_dump(mode="json")}),
        ]
        self.calls: list[str] = []

    def execute(self, module_type, input_payload, config):
        expected_type, output = self.outputs.pop(0)
        if module_type != expected_type:
            raise AssertionError(f"expected {expected_type}, received {module_type}")
        self.calls.append(module_type)
        return output


class ExistingRagPipelineModulesTests(unittest.TestCase):
    def test_load_index_reuses_loaded_collection_for_same_index(self) -> None:
        # Given
        registry = FakeModuleRegistry()
        loader_output = registry.outputs[1]
        registry.outputs = [loader_output]
        modules = ExistingRagPipelineModules(registry)

        # When
        first = modules.load_index("index-1")
        second = modules.load_index("index-1")

        # Then
        self.assertIs(first, second)
        self.assertEqual(registry.calls, ["pgvector_collection_loader"])

    def test_registry_bridge_calls_existing_module_types_through_context(self) -> None:
        # Given
        registry = FakeModuleRegistry()
        adapter = ExistingRagPipelineAdapter(ExistingRagPipelineModules(registry))

        # When
        result = adapter.retrieve(retrieval_request())

        # Then
        self.assertEqual(registry.calls[-1], "context")
        self.assertEqual(result.index_id, "index-1")
        self.assertEqual(result.cells[0].cell_id, "income:B12")


if __name__ == "__main__":
    unittest.main()
