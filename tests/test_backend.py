import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from PIL import Image
from pydantic import ValidationError

from app import app
from backend.answer_cache import AnswerCacheRepository
from backend.api.spreadsheet_artifact_routes import create_spreadsheet_artifact_router
from backend.chat_completion import ChatCompletionError
from backend.embedding_artifacts import EmbeddingArtifactStore
from backend.vector_index_store import VectorIndexStore
from backend.module_registry import ModuleRegistry
from backend.module_documentation import MODULE_DOCS_DIR, render_module_markdown
from backend.module_worker import ModuleWorkerCancelled
from backend.openai_responses_vision import OpenAIResponsesVisionClient
from backend.modules.decomposer import DecomposerModule
from backend.modules.bfs_llm_structure_detector import BfsLlmStructureDetectorModule
from backend.modules.dense_retriever import DenseRetrieverModule
from backend.modules.embedder import EmbedderModule
from backend.modules.cell_text_embedder import CellTextEmbedderModule
from backend.modules.cell_text_serializer import CellTextSerializerModule
from backend.modules.context_expander import ContextExpanderModule
from backend.modules.docling_table_detector import DoclingTableDetectorModule
from backend.modules.exhaustive_cell_text_serializer import (
    ExhaustiveCellTextSerializerModule,
)
from backend.modules.local_vlm_structure_detector import LocalVlmStructureDetectorModule
from backend.modules.luna_vlm_structure_detector import LunaVlmStructureDetectorModule
from backend.modules.luna_vlm_structure_detector import LUNA_SHEET_RESPONSE_SCHEMA
from backend.modules.base import ModuleExecutionError
from backend.modules.openpyxl_region_detector import OpenpyxlRegionDetectorModule
from backend.modules.processed_file_selector import ProcessedFileSelectorModule
from backend.modules.reader import ReaderModule
from backend.modules.rrf_fusion import RrfFusionModule
from backend.modules.adaptive_query_decomposer import AdaptiveQueryDecomposerModule
from backend.modules.semantic_scoped_dense_retriever import SemanticScopedDenseRetrieverModule
from backend.semantic_matching.catalog import QueryExample
from backend.semantic_matching.matcher import SemanticQueryMatcher
from backend.modules.vector_index_writer import VectorIndexWriterModule
from backend.routes import create_api_router
from backend.similarity import combined_similarity, rank_candidates
from backend.spreadsheets.workbook_catalog import WorkbookCatalog
from backend.spreadsheets.cell_visibility import WorksheetVisibility
from backend.spreadsheets.table_geometry import bbox_to_cell_bounds, compute_sheet_layout
from backend.spreadsheets.exhaustive_tiling import build_exhaustive_tiles
from backend.workflows.executor import (
    DagExecutionCancelled,
    DagExecutionError,
    WorkflowExecutor,
)
from backend.workflows.models import (
    CanvasPosition,
    WorkflowEdge,
    WorkflowExecutionRequest,
    WorkflowGraph,
    WorkflowNode,
    WorkflowSaveRequest,
)
from backend.workflows.store import ResultCache, RunStore, WorkflowStore


class StubCompletionClient:
    def complete(self, model, messages):
        return '["Sheet: ? | Row Header: Test Metric | Column Header: ? | Cell Value: ?"]'


class StubEmbeddingEncoder:
    def encode(self, queries):
        return [
            [float(index + 1), float(len(query))]
            for index, query in enumerate(queries)
        ]


class BlockingModuleWorker:
    """Test double that only returns after the executor requests termination."""

    def __init__(self):
        self.started = Event()
        self.terminated = Event()
        self.execution_id = None

    def execute(self, module_type, input_payload, config, execution_id):
        self.execution_id = execution_id
        self.started.set()
        self.terminated.wait(timeout=5)
        raise ModuleWorkerCancelled("test worker terminated")

    def cancel(self, execution_id):
        if execution_id != self.execution_id:
            return False
        self.terminated.set()
        return True

    def reset(self):
        self.terminated.set()
        return True


class OpenAIResponsesVisionClientTests(unittest.TestCase):
    def test_structured_vision_request_uses_responses_api_contract(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps({
                    "status": "completed",
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": '{"tables":[]}',
                        }],
                    }],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 5,
                        "total_tokens": 105,
                    },
                }).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        with TemporaryDirectory() as directory:
            sheet_image = Path(directory) / "sheet.png"
            Image.new("RGB", (8, 6), "white").save(sheet_image)
            client = OpenAIResponsesVisionClient(
                api_key="test-key",
                base_url="https://api.openai.com/v1",
            )
            with patch(
                "backend.openai_responses_vision.urlopen",
                side_effect=fake_urlopen,
            ):
                result = client.complete_structured(
                    model="gpt-5.6-luna",
                    system_prompt="system",
                    user_prompt="user",
                    image_path=sheet_image,
                    schema_name="luna_spreadsheet_sheet",
                    json_schema=LUNA_SHEET_RESPONSE_SCHEMA,
                    reasoning_effort="low",
                    max_output_tokens=6000,
                    timeout_seconds=240,
                )

        request = captured["request"]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(captured["timeout"], 240)
        self.assertFalse(body["store"])
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        image_inputs = body["input"][0]["content"][1:]
        self.assertEqual([item["detail"] for item in image_inputs], ["original"])
        self.assertTrue(all(item["image_url"].startswith("data:image/png;base64,") for item in image_inputs))
        self.assertEqual(result.content, '{"tables":[]}')
        self.assertEqual(result.usage["total_tokens"], 105)


def sample_cell_documents():
    def item(cell_id, cell_coord, row_header, value):
        text = (
            f"Sheet: Key_Stats | Row Header: {row_header} | "
            f"Column Header: LTM | Cell Value: {value}"
        )
        return {
            "cell_id": cell_id,
            "sheet_name": "Key_Stats",
            "cell_coord": cell_coord,
            "row_header": [row_header],
            "column_header": ["LTM"],
            "cell_value": value,
            "variant": "header_with_value",
            "text": text,
        }

    return {
        "file_name": "sample.xlsx",
        "workbook_hash": "test-workbook-hash",
        "items": [
            item("KS Cell A1", "A1", "Test Metric", "100"),
            item("KS Cell B2", "B2", "Other Metric", "200"),
            item("KS Cell C3", "C3", "Unrelated Value", "300"),
        ],
    }


def sample_query_context(
    question_id: str = "QUERY-TEST",
    question_text: str = "테스트 지표는 얼마인가?",
):
    return {
        "question_id": question_id,
        "question_text": question_text,
    }


def sample_document_context():
    return {
        "file_name": "sample.xlsx",
        "workbook_hash": "test-workbook-hash",
    }


class SimilarityTests(unittest.TestCase):
    def test_identical_questions_have_maximum_similarity(self) -> None:
        combined, sequence, jaccard = combined_similarity("IBM 시가총액", "IBM 시가총액")
        self.assertEqual(combined, 1.0)
        self.assertEqual(sequence, 1.0)
        self.assertEqual(jaccard, 1.0)

    def test_candidates_are_ranked_from_highest_score(self) -> None:
        matches = rank_candidates(
            "IBM 시가총액",
            [("Q1", "Apple 매출"), ("Q2", "IBM 시가총액")],
        )
        self.assertEqual(matches[0].question_id, "Q2")


class SemanticQueryMatcherTests(unittest.TestCase):
    class KeywordEncoder:
        def encode(self, queries):
            return [
                [1.0, 0.0] if "revenue" in query.lower() else [0.0, 1.0]
                for query in queries
            ]

    def test_route_votes_for_nearby_examples_and_returns_sheet_scope(self) -> None:
        matcher = SemanticQueryMatcher(self.KeywordEncoder(), examples=(
            QueryExample("q1", "revenue trend", "financials", ("Key_Stats",)),
            QueryExample("q2", "revenue growth", "financials", ("Key_Stats",)),
            QueryExample("q3", "employee count", "headcount", ("Employees",)),
        ))

        decision = matcher.route("revenue this year", "test", 0.74, 3, 0.05)

        self.assertEqual(decision.target, "financials")
        self.assertEqual(decision.sheets, ("Key_Stats",))
        self.assertEqual(len(decision.matches), 3)

    def test_route_falls_back_below_confidence_threshold(self) -> None:
        matcher = SemanticQueryMatcher(self.KeywordEncoder(), examples=(
            QueryExample("q1", "employee count", "headcount", ("Employees",)),
        ))

        decision = matcher.route("revenue this year", "test", 0.74, 1, 0.05)

        self.assertIsNone(decision.target)
        self.assertEqual(decision.sheets, ())

    def test_scoped_dense_retriever_falls_back_when_no_matching_sheet_exists(self) -> None:
        with TemporaryDirectory() as directory:
            store = VectorIndexStore(Path(directory))
            index_id = "a" * 64
            metadata = {
                "workbook_hash": "hash", "model": "test", "dimension": 2,
                "document_count": 1, "items": [{
                    "cell_id": "Other Cell A1", "sheet_name": "Other", "cell_coord": "A1",
                    "row_header": ["Revenue"], "column_header": ["LTM"],
                    "cell_value": "100", "variant": "header_with_value", "text": "Revenue",
                    "embedding_index": 0,
                }],
            }
            store.put(index_id, [[1.0, 0.0]], metadata)
            result = SemanticScopedDenseRetrieverModule(store).run({
                "query_input": {"question_id": "q", "items": {"Revenue": [1.0, 0.0]}},
                "index_input": {"index_id": index_id, "workbook_hash": "hash", "model": "test", "dimension": 2, "document_count": 1},
                "semantic_match": {"matched": True, "target": "financials", "confidence": 0.9, "sheets": ["Key_Stats"], "reason": "test", "matches": []},
            })
        self.assertEqual(result["items"][0]["cell_id"], "Other Cell A1")

    def test_adaptive_decomposer_skips_llm_when_semantic_match_succeeds(self) -> None:
        class FailingCompletionClient:
            def complete(self, model, messages):
                raise AssertionError("LLM must not be called for a confident match")

        result = AdaptiveQueryDecomposerModule(FailingCompletionClient()).run({
            "question_text": "IBM revenue trend",
            "semantic_match": {
                "matched": True, "target": "financials", "confidence": 0.9,
                "sheets": ["Key_Stats"], "reason": "test", "matches": [],
            },
        })
        self.assertEqual(result["subqueries"], ["IBM revenue trend"])


class ModularRagArchitectureTests(unittest.TestCase):
    def test_rrf_fuses_ranks_within_the_same_subquery(self) -> None:
        def candidate(rank, cell_id, subquery):
            return {
                "rank": rank,
                "cell_id": cell_id,
                "score": 1.0 / rank,
                "text": f"Row Header: {cell_id}",
                "matched_subquery": subquery,
            }

        result = RrfFusionModule().run(
            {
                "bm25_result": {
                    "query_context": sample_query_context("QUERY-RRF"),
                    "document_context": sample_document_context(),
                    "items": [candidate(1, "KS Cell A1", "query-a")],
                },
                "dense_result": {
                    "query_context": sample_query_context("QUERY-RRF"),
                    "document_context": sample_document_context(),
                    "items": [candidate(1, "KS Cell A1", "query-b")],
                },
            }
        )

        self.assertAlmostEqual(result["items"][0]["rrf_score"], 1 / 61, places=9)

    def test_rrf_rejects_results_from_different_documents(self) -> None:
        branch = {
            "query_context": sample_query_context("QUERY-LINEAGE"),
            "document_context": sample_document_context(),
            "items": [],
        }
        mismatched = {
            **branch,
            "document_context": {
                "file_name": "other.xlsx",
                "workbook_hash": "other-hash",
            },
        }

        with self.assertRaisesRegex(ModuleExecutionError, "document_context"):
            RrfFusionModule().run(
                {"bm25_result": branch, "dense_result": mismatched}
            )

    def test_context_expander_uses_rrf_cells_and_adjacent_document_rows(self) -> None:
        context = ContextExpanderModule().run(
            {
                "retrieval_json": {
                    "query_context": sample_query_context(),
                    "document_context": sample_document_context(),
                    "items": [
                        {
                            "rank": 1,
                            "cell_id": "KS Cell A1",
                            "rrf_score": 0.03,
                            "text": "matched",
                            "matched_subquery": "metric",
                        }
                    ],
                },
                "document_input": sample_cell_documents(),
                "top_k": 100,
                "adjacent_radius": 1,
                "max_blocks": 100,
            }
        )["context_json"]

        rendered = "\n\n".join(context["context_blocks"])
        self.assertEqual(context["query_context"]["question_id"], "QUERY-TEST")
        self.assertEqual(context["document_context"], sample_document_context())
        self.assertEqual(context["block_count"], 2)
        self.assertIn("KS Cell A1", rendered)
        self.assertIn("KS Cell B2", rendered)
        self.assertNotIn("KS Cell C3", rendered)
        self.assertIn("100", rendered)

    def test_reader_generates_from_question_and_expanded_context(self) -> None:
        class CapturingCompletionClient:
            def __init__(self):
                self.messages = []

            def complete(self, model, messages):
                self.messages = messages
                return "테스트 답변입니다. [KS Cell A1]"

        client = CapturingCompletionClient()
        answer = ReaderModule(client).run(
            {
                "context_json": {
                    "query_context": sample_query_context(),
                    "document_context": sample_document_context(),
                    "top_k_used": 1,
                    "adjacent_radius": 3,
                    "context_characters": 40,
                    "context_blocks": ["[LTM (KS Cell A1)]: 100"],
                    "block_count": 1,
                },
            }
        )["answer_json"]

        prompt = "\n".join(message["content"] for message in client.messages)
        self.assertIn("테스트 지표는 얼마인가?", prompt)
        self.assertIn("KS Cell A1", prompt)
        self.assertEqual(answer["answer"], "테스트 답변입니다. [KS Cell A1]")

    def test_document_vectors_are_external_float32_artifacts(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            store = EmbeddingArtifactStore(Path(temporary_directory))
            output = CellTextEmbedderModule(
                StubEmbeddingEncoder(),
                store,
            ).run(sample_cell_documents())

            artifact_path = Path(temporary_directory) / f"{output['artifact_id']}.f32"
            self.assertTrue(artifact_path.is_file())
            self.assertEqual(artifact_path.stat().st_size, len(output["items"]) * 2 * 4)
            self.assertEqual(output["dimension"], 2)
            self.assertTrue(
                all("embedding" not in item for item in output["items"])
            )

    def test_vector_index_persists_and_dense_retriever_uses_only_its_reference(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            artifact_store = EmbeddingArtifactStore(root / "embeddings")
            index_store = VectorIndexStore(root / "vector-db")
            document_embeddings = CellTextEmbedderModule(
                StubEmbeddingEncoder(),
                artifact_store,
            ).run(sample_cell_documents())
            index_reference = VectorIndexWriterModule(
                artifact_store,
                index_store,
            ).run(document_embeddings)

            self.assertEqual(
                set(index_reference),
                {"index_id", "file_name", "workbook_hash", "model", "dimension", "document_count"},
            )
            self.assertTrue(
                (root / "vector-db" / f"{index_reference['index_id']}.npy").is_file()
            )
            restarted_dense = DenseRetrieverModule(
                VectorIndexStore(root / "vector-db")
            ).run(
                {
                    "query_input": {
                        "query_context": sample_query_context("QUERY-PERSISTED"),
                        "items": {"Test Metric": [1.0, 11.0]},
                    },
                    "index_input": index_reference,
                }
            )
            self.assertTrue(restarted_dense["items"])
            self.assertEqual(
                restarted_dense["query_context"]["question_id"],
                "QUERY-PERSISTED",
            )


class RepositoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.embedding_artifact_directory = TemporaryDirectory()
        cls.vector_index_directory = TemporaryDirectory()
        cls.repository = AnswerCacheRepository()
        cls.question_text = "IBM의 LTM 기준 시가총액과 TEV는 각각 얼마인가?"
        cls.repository.save_cached_answer(
            "Q001", cls.question_text, "Test LLM Answer"
        )
        cls.module_registry = ModuleRegistry(
            cls.repository,
            StubCompletionClient(),
            StubEmbeddingEncoder(),
            EmbeddingArtifactStore(
                Path(cls.embedding_artifact_directory.name)
            ),
            VectorIndexStore(Path(cls.vector_index_directory.name)),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.embedding_artifact_directory.cleanup()
        cls.vector_index_directory.cleanup()

    def test_registry_exposes_all_frontend_modules(self) -> None:
        definitions = self.module_registry.definitions()
        self.assertEqual(len(definitions), 25)
        self.assertEqual(
            {definition["type"] for definition in definitions},
            {
                "query_input",
                "decomposer",
                "adaptive_query_decomposer",
                "embedder",
                "cell_text_embedder",
                "vector_index_writer",
                "bm25_retriever",
                "dense_retriever",
                "rrf_fusion",
                "semantic_query_matcher",
                "semantic_scoped_dense_retriever",
                "context",
                "reader",
                "answer_cache_writer",
                "json_transformer",
                "json_inspector",
                "processed_file_selector",
                "bfs_llm_structure_detector",
                "local_vlm_structure_detector",
                "luna_vlm_structure_detector",
                "docling_table_detector",
                "openpyxl_region_detector",
                "cell_text_serializer",
                "exhaustive_cell_text_serializer",
                "prebuilt_index_loader",
                "dataframe_source",
                "image_tile_source",
                "qa_example_loader",
            },
        )

    def test_registered_modules_declare_dto_layers_explicitly(self) -> None:
        for definition in self.module_registry.definitions():
            module = self.module_registry.get(definition["type"])
            module_class = type(module)
            with self.subTest(module_type=definition["type"]):
                self.assertIn("input_model", module_class.__dict__)
                self.assertIn("config_model", module_class.__dict__)
                self.assertIn("execution_model", module_class.__dict__)
                self.assertTrue(module_class.__doc__)
                self.assertTrue(module.input_model.__name__.endswith("InputDTO"))
                self.assertTrue(module.config_model.__name__.endswith("ConfigDTO"))
                self.assertIsNot(module.input_model, module.output_model)
                self.assertTrue(
                    set(module.input_model.model_fields).isdisjoint(
                        module.config_model.model_fields
                    )
                )

    def test_checked_in_module_guides_match_live_contracts(self) -> None:
        expected_files = {
            f"{definition['type']}.md"
            for definition in self.module_registry.definitions()
        }
        actual_files = {path.name for path in MODULE_DOCS_DIR.glob("*.md")} - {
            "README.md"
        }
        self.assertEqual(actual_files, expected_files)

        for definition in self.module_registry.definitions():
            with self.subTest(module_type=definition["type"]):
                module = self.module_registry.get(definition["type"])
                self.assertEqual(
                    (MODULE_DOCS_DIR / f"{definition['type']}.md").read_text(
                        encoding="utf-8"
                    ),
                    render_module_markdown(module),
                )

    def test_pipeline_modules_execute_with_named_io(self) -> None:
        query_context = sample_query_context(
            "QUERY-INTEGRATION",
            self.question_text,
        )
        decomposed = self.module_registry.execute(
            "decomposer",
            {"query_context": query_context},
        )
        embedded = self.module_registry.execute(
            "embedder", decomposed
        )
        document_input = sample_cell_documents()
        bm25_result = self.module_registry.execute(
            "bm25_retriever",
            {
                "query_input": decomposed,
                "document_input": document_input,
            },
        )
        document_embeddings = self.module_registry.execute(
            "cell_text_embedder",
            document_input,
        )
        vector_index = self.module_registry.execute(
            "vector_index_writer",
            document_embeddings,
        )
        dense_result = self.module_registry.execute(
            "dense_retriever",
            {
                "query_input": embedded,
                "index_input": vector_index,
            },
        )
        retrieved = self.module_registry.execute(
            "rrf_fusion",
            {"bm25_result": bm25_result, "dense_result": dense_result},
        )
        context = self.module_registry.execute(
            "context",
            {
                "retrieval_json": retrieved,
                "document_input": document_input,
            },
        )
        answer = self.module_registry.execute(
            "reader",
            {"context_json": context["context_json"]},
        )
        cached_answer = self.module_registry.execute(
            "answer_cache_writer",
            {"answer_json": answer["answer_json"]},
        )

        self.assertEqual(
            set(decomposed),
            {"query_context", "subqueries"},
        )
        self.assertEqual(set(embedded), {"query_context", "items"})
        self.assertEqual(len(embedded["items"]), len(decomposed["subqueries"]))
        self.assertEqual(
            set(embedded["items"]),
            set(decomposed["subqueries"]),
        )
        self.assertEqual(
            set(bm25_result),
            {"query_context", "document_context", "items"},
        )
        self.assertEqual(
            set(document_embeddings),
            {
                "file_name",
                "workbook_hash",
                "model",
                "artifact_id",
                "dimension",
                "items",
            },
        )
        self.assertEqual(
            len(document_embeddings["items"]),
            len(document_input["items"]),
        )
        self.assertIn("embedding_index", document_embeddings["items"][0])
        self.assertEqual(document_embeddings["dimension"], 2)
        self.assertEqual(
            set(vector_index),
            {"index_id", "file_name", "workbook_hash", "model", "dimension", "document_count"},
        )
        self.assertEqual(vector_index["document_count"], len(document_input["items"]))
        self.assertEqual(
            set(dense_result),
            {"query_context", "document_context", "items"},
        )
        self.assertEqual(
            set(retrieved),
            {"query_context", "document_context", "items"},
        )
        self.assertEqual(bm25_result["items"][0]["cell_id"], "KS Cell A1")
        self.assertTrue(dense_result["items"])
        self.assertTrue(retrieved["items"])
        self.assertIn("context_json", context)
        self.assertIn("answer_json", answer)
        self.assertEqual(cached_answer, answer)
        self.assertEqual(
            self.repository.get_cached_answer(
                answer["answer_json"]["query_context"]["question_id"]
            ),
            answer["answer_json"]["answer"],
        )

    def test_source_modules_execute_with_named_io(self) -> None:
        query_result = self.module_registry.execute(
            "query_input", {"query": self.question_text}
        )

        self.assertEqual(
            query_result,
            {
                "cached_answer": {
                    "query_context": {
                        "question_id": "Q001",
                        "question_text": self.question_text,
                    },
                    "answer": "Test LLM Answer",
                }
            },
        )

    def test_json_transformer_and_inspector_execute_independently(self) -> None:
        transformed = self.module_registry.execute(
            "json_transformer",
            {
                "any_json": {"question": "value", "keep": 1},
                "mappings": {"question": "user_query"},
            },
        )["transformed_json"]
        inspected = self.module_registry.execute(
            "json_inspector", transformed
        )

        self.assertEqual(transformed, {"user_query": "value", "keep": 1})
        self.assertEqual(inspected, transformed)

    def test_cached_answers_survive_repository_restart(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cache_path = root / "cache" / "answers.json"
            repository = AnswerCacheRepository(cache_path)
            repository.save_cached_answer("Q-CUSTOM", "사용자 질문", "저장된 답변")

            restarted = AnswerCacheRepository(cache_path)

            self.assertEqual(restarted.get_cached_answer("Q-CUSTOM"), "저장된 답변")
            self.assertIn(("Q-CUSTOM", "사용자 질문"), restarted.question_candidates())
            self.assertEqual(restarted.clear_cached_answers(), 1)
            self.assertFalse(cache_path.exists())


class ApiContractTests(unittest.TestCase):
    client = TestClient(app)

    def test_module_definitions_are_available_to_frontend(self) -> None:
        response = self.client.get("/api/modules")
        self.assertEqual(response.status_code, 200)
        modules = response.json()["modules"]
        self.assertEqual(len(modules), 25)
        for module in modules:
            self.assertIn("input_schema", module)
            self.assertIn("config_schema", module)
            self.assertIn("output_schema", module)
            self.assertIn("execution_schema", module)
            self.assertIn("branch_schemas", module)
            self.assertIn("properties", module["config_schema"])
            if module["raw_input"]:
                self.assertNotIn("properties", module["input_schema"])
            else:
                self.assertIn("properties", module["input_schema"])
                self.assertTrue(
                    set(module["input_schema"]["properties"]).isdisjoint(
                        module["config_schema"]["properties"]
                    )
                )
            self.assertTrue(
                "properties" in module["output_schema"]
                or "anyOf" in module["output_schema"]
                or module["raw_output"]
            )

    def test_module_detail_exposes_named_dto_fields(self) -> None:
        response = self.client.get("/api/modules/query_input")

        self.assertEqual(response.status_code, 200)
        contract = response.json()
        self.assertEqual(set(contract["input_schema"]["properties"]), {"query"})
        self.assertEqual(set(contract["config_schema"]["properties"]), {"threshold"})
        self.assertEqual(
            contract["documentation_url"],
            "/api/modules/query_input/docs",
        )
        self.assertEqual(
            contract["branch_outputs"],
            {"cached": "cached_answer", "generated": "query_context"},
        )
        self.assertEqual(
            set(contract["branch_schemas"]["cached"]["properties"]),
            {"cached_answer"},
        )
        self.assertEqual(
            set(contract["branch_schemas"]["generated"]["properties"]),
            {"query_context"},
        )
        self.assertNotIn("failed", contract["branch_schemas"])
        self.assertEqual(contract["config_fields"], ["threshold"])
        self.assertEqual(
            set(contract["execution_schema"]["properties"]),
            {"input", "config"},
        )

        decomposer = self.client.get("/api/modules/decomposer").json()
        self.assertEqual(
            set(decomposer["input_schema"]["properties"]),
            {"query_context"},
        )
        self.assertEqual(
            set(decomposer["config_schema"]["properties"]),
            {"model", "preset", "system_prompt", "user_prompt_template"},
        )
        self.assertEqual(
            set(decomposer["output_schema"]["properties"]),
            {"query_context", "subqueries"},
        )
        self.assertEqual(decomposer["outputs"], ["output"])
        self.assertTrue(decomposer["raw_output"])

        embedder = self.client.get("/api/modules/embedder").json()
        self.assertEqual(
            set(embedder["input_schema"]["properties"]),
            {"query_context", "subqueries"},
        )
        self.assertEqual(
            set(embedder["config_schema"]["properties"]),
            {"model"},
        )
        self.assertEqual(
            embedder["config_schema"]["properties"]["model"]["default"],
            "BAAI/bge-large-en-v1.5",
        )
        self.assertEqual(
            set(embedder["output_schema"]["properties"]),
            {"query_context", "items"},
        )
        items_schema = embedder["output_schema"]["properties"]["items"]
        self.assertEqual(items_schema["type"], "object")
        self.assertEqual(items_schema["additionalProperties"]["type"], "array")
        self.assertEqual(items_schema["additionalProperties"]["items"]["type"], "number")
        self.assertEqual(embedder["outputs"], ["output"])
        self.assertTrue(embedder["raw_output"])

        document_embedder = self.client.get("/api/modules/cell_text_embedder").json()
        self.assertEqual(document_embedder["inputs"], ["input"])
        self.assertEqual(
            set(document_embedder["input_schema"]["properties"]),
            {"file_name", "workbook_hash", "items"},
        )
        self.assertEqual(
            set(document_embedder["config_schema"]["properties"]),
            {"model", "batch_size"},
        )
        embedded_item_reference = document_embedder["output_schema"]["properties"]["items"]["items"]["$ref"]
        embedded_item_definition = embedded_item_reference.rsplit("/", 1)[-1]
        embedded_item_schema = document_embedder["output_schema"]["$defs"][embedded_item_definition]
        self.assertEqual(
            set(embedded_item_schema["properties"]),
            {
                "cell_id",
                "sheet_name",
                "cell_coord",
                "row_header",
                "column_header",
                "cell_value",
                "variant",
                "text",
                "embedding_index",
            },
        )
        self.assertEqual(
            set(document_embedder["output_schema"]["properties"]),
            {
                "file_name",
                "workbook_hash",
                "model",
                "artifact_id",
                "dimension",
                "items",
            },
        )

        bm25 = self.client.get("/api/modules/bm25_retriever").json()
        self.assertEqual(bm25["inputs"], ["query_input", "document_input"])
        self.assertEqual(
            set(bm25["input_schema"]["properties"]),
            {"query_input", "document_input"},
        )
        self.assertEqual(set(bm25["config_schema"]["properties"]), {"k1", "b", "top_k"})

        dense = self.client.get("/api/modules/dense_retriever").json()
        self.assertEqual(dense["inputs"], ["query_input", "index_input"])
        self.assertEqual(
            set(dense["input_schema"]["properties"]),
            {"query_input", "index_input"},
        )
        self.assertEqual(
            set(dense["config_schema"]["properties"]),
            {"top_k"},
        )

        rrf = self.client.get("/api/modules/rrf_fusion").json()
        self.assertEqual(rrf["inputs"], ["bm25_result", "dense_result"])
        self.assertEqual(
            set(rrf["input_schema"]["properties"]),
            {"bm25_result", "dense_result"},
        )
        self.assertEqual(
            set(rrf["config_schema"]["properties"]),
            {"rrf_k", "top_k", "ratio_penalty"},
        )
        self.assertEqual(
            set(rrf["output_schema"]["properties"]),
            {"query_context", "document_context", "items"},
        )
        self.assertTrue(rrf["raw_output"])

        docling = self.client.get("/api/modules/docling_table_detector").json()
        self.assertEqual(
            set(docling["output_schema"]["properties"]),
            {"file_name", "workbook_hash", "tables"},
        )
        table_reference = docling["output_schema"]["properties"]["tables"]["items"]["$ref"]
        table_definition = table_reference.rsplit("/", 1)[-1]
        table_schema = docling["output_schema"]["$defs"][table_definition]
        self.assertEqual(
            set(table_schema["properties"]),
            {"sheet_name", "table_index", "excel_range", "bbox_px", "cell_bounds"},
        )

        serializer = self.client.get("/api/modules/cell_text_serializer").json()
        self.assertEqual(
            set(serializer["output_schema"]["properties"]),
            {"file_name", "workbook_hash", "items"},
        )
        item_reference = serializer["output_schema"]["properties"]["items"]["items"]["$ref"]
        item_definition = item_reference.rsplit("/", 1)[-1]
        item_schema = serializer["output_schema"]["$defs"][item_definition]
        self.assertEqual(
            set(item_schema["properties"]),
            {
                "cell_id",
                "sheet_name",
                "cell_coord",
                "row_header",
                "column_header",
                "cell_value",
                "variant",
                "text",
            },
        )

    def test_swagger_exposes_exact_per_module_execution_models(self) -> None:
        openapi = self.client.get("/openapi.json").json()
        execute_path = openapi["paths"]["/api/modules/decomposer/execute"]["post"]
        request_schema = execute_path["requestBody"]["content"][
            "application/json"
        ]["schema"]
        response_schema = execute_path["responses"]["200"]["content"][
            "application/json"
        ]["schema"]

        self.assertTrue(
            request_schema["$ref"].endswith("/DecomposerExecutionRequestDTO")
        )
        self.assertTrue(response_schema["$ref"].endswith("/SubqueriesDTO"))
        self.assertEqual(self.client.get("/docs").status_code, 200)

    def test_generated_module_markdown_is_available_through_api(self) -> None:
        response = self.client.get("/api/modules/context/docs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("# Context Expander", response.text)
        self.assertIn("## Input DTO", response.text)
        self.assertIn("document_context", response.text)

    def test_every_module_separates_connection_inputs_from_node_config(self) -> None:
        expected = {
            "query_input": ({"query"}, {"threshold"}),
            "decomposer": (
                {"query_context"},
                {"model", "preset", "system_prompt", "user_prompt_template"},
            ),
            "embedder": (
                {"query_context", "subqueries"},
                {"model"},
            ),
            "cell_text_embedder": (
                {"file_name", "workbook_hash", "items"},
                {"model", "batch_size"},
            ),
            "vector_index_writer": (
                {"file_name", "workbook_hash", "model", "artifact_id", "dimension", "items"},
                set(),
            ),
            "prebuilt_index_loader": ({"file_name"}, set()),
            "bm25_retriever": (
                {"query_input", "document_input"},
                {"k1", "b", "top_k"},
            ),
            "dense_retriever": (
                {"query_input", "index_input"},
                {"top_k"},
            ),
            "rrf_fusion": (
                {"bm25_result", "dense_result"},
                {"rrf_k", "top_k", "ratio_penalty"},
            ),
            "context": (
                {"retrieval_json", "document_input"},
                {"top_k", "adjacent_radius", "max_blocks"},
            ),
            "reader": (
                {"context_json"},
                {"model", "preset", "system_prompt", "user_prompt_template"},
            ),
            "answer_cache_writer": (
                {"answer_json"},
                set(),
            ),
            "json_transformer": ({"any_json"}, {"mappings"}),
            "json_inspector": (set(), set()),
            "processed_file_selector": ({"file_name"}, set()),
            "bfs_llm_structure_detector": (
                {"file_name", "workbook_hash", "sheet_names"},
                {
                    "model",
                    "max_rows",
                    "max_columns",
                    "merge_gap",
                    "min_non_empty_cells",
                    "min_table_columns",
                    "header_candidate_rows",
                    "llm_batch_size",
                    "system_prompt",
                    "user_prompt_template",
                },
            ),
            "local_vlm_structure_detector": (
                {"file_name", "workbook_hash", "sheet_names"},
                {
                    "model",
                    "max_rows",
                    "max_columns",
                    "max_context_cells",
                    "context_window",
                    "timeout_seconds",
                    "validation_retries",
                    "system_prompt",
                    "user_prompt_template",
                },
            ),
            "luna_vlm_structure_detector": (
                {"file_name", "workbook_hash", "sheet_names"},
                {
                    "model",
                    "max_rows",
                    "max_columns",
                    "max_context_cells",
                    "reasoning_effort",
                    "max_output_tokens",
                    "timeout_seconds",
                    "validation_retries",
                    "system_prompt",
                    "user_prompt_template",
                },
            ),
            "docling_table_detector": (
                {"file_name", "workbook_hash", "sheet_names"},
                {"max_rows", "max_columns"},
            ),
            "openpyxl_region_detector": (
                {"file_name", "workbook_hash", "tables"},
                {
                    "header_scan_rows",
                    "bold_ratio_threshold",
                    "fill_ratio_threshold",
                },
            ),
            "cell_text_serializer": (
                {"file_name", "workbook_hash", "tables"},
                set(),
            ),
            "exhaustive_cell_text_serializer": (
                {"file_name", "workbook_hash", "sheet_names"},
                {
                    "variant_mode",
                    "deduplicate_header_values",
                    "max_documents",
                },
            ),
            "dataframe_source": (
                {"file_name"},
                {"sample_rows", "max_sheets"},
            ),
            "image_tile_source": (
                {"file_name", "sheet_name"},
                {"tile_height_px", "max_tiles"},
            ),
            "qa_example_loader": (
                {"file_name"},
                {"include_builtin"},
            ),
        }

        registered_types = {
            module["type"] for module in self.client.get("/api/modules").json()["modules"]
        }
        self.assertEqual(set(expected), registered_types)

        for module_type, (input_fields, config_fields) in expected.items():
            with self.subTest(module_type=module_type):
                contract = self.client.get(f"/api/modules/{module_type}").json()
                actual_inputs = set(contract["input_schema"].get("properties", {}))
                actual_config = set(contract["config_schema"].get("properties", {}))
                self.assertEqual(actual_inputs, input_fields)
                self.assertEqual(actual_config, config_fields)
                self.assertTrue(actual_inputs.isdisjoint(actual_config))
                self.assertEqual(set(contract["config_fields"]), config_fields)
                self.assertFalse(
                    set(contract["config_schema"].get("required", [])),
                    "Config DTO는 독립 실행 가능한 기본값을 가져야 합니다",
                )
                self.assertTrue(
                    {"file_name", "workbook_hash", "sheet_name", "sheet_names"}.isdisjoint(
                        actual_config
                    ),
                    "데이터 식별자는 Config가 아니라 Input DTO여야 합니다",
                )

        inspector = self.client.get("/api/modules/json_inspector").json()
        self.assertTrue(inspector["raw_input"])
        self.assertTrue(inspector["raw_output"])
        self.assertNotIn("properties", inspector["input_schema"])
        self.assertNotIn("properties", inspector["output_schema"])

        decomposer = self.client.get("/api/modules/decomposer").json()
        self.assertEqual(
            {preset["id"] for preset in decomposer["config_presets"]},
            {"luna_decomposer", "rdb_financial", "simple_decomposer"},
        )

    def test_module_can_be_executed_independently(self) -> None:
        response = self.client.post(
            "/api/modules/json_transformer/execute",
            json={
                "input": {"any_json": {"source": 7}},
                "config": {"mappings": {"source": "target"}},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transformed_json"], {"target": 7})

    def test_independent_execution_rejects_mixed_input_and_config_layers(self) -> None:
        config_in_input = self.client.post(
            "/api/modules/json_transformer/execute",
            json={
                "input": {
                    "any_json": {"source": 7},
                    "mappings": {"source": "target"},
                },
                "config": {},
            },
        )
        input_in_config = self.client.post(
            "/api/modules/json_transformer/execute",
            json={
                "input": {"any_json": {"source": 7}},
                "config": {"any_json": {}},
            },
        )

        self.assertEqual(config_in_input.status_code, 422)
        self.assertEqual(input_in_config.status_code, 422)

    def test_generic_source_module_is_registered_and_independently_executable(self) -> None:
        response = self.client.post(
            "/api/modules/qa_example_loader/execute",
            json={"input": {}, "config": {"include_builtin": True}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["total_count"], 0)

    def test_json_transformer_starts_with_an_empty_mapping(self) -> None:
        response = self.client.post(
            "/api/modules/json_transformer/execute",
            json={"input": {"any_json": {"source": 7}}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transformed_json"], {"source": 7})

    def test_json_inspector_accepts_and_returns_the_raw_json_value(self) -> None:
        source = [{"row": 1}, {"row": 2}]
        response = self.client.post(
            "/api/modules/json_inspector/execute",
            json={"input": source},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), source)

    def test_embedder_accepts_and_returns_an_unwrapped_dto(self) -> None:
        result = EmbedderModule(StubEmbeddingEncoder()).run(
            {
                "query_context": sample_query_context(),
                "subqueries": [
                    "Sheet: ? | Row Header: Revenue | Column Header: LTM | Cell Value: ?"
                ],
            }
        )

        self.assertEqual(set(result), {"query_context", "items"})
        self.assertEqual(
            result["items"][
                "Sheet: ? | Row Header: Revenue | Column Header: LTM | Cell Value: ?"
            ],
            [1.0, 67.0],
        )

    def test_decomposer_normalizes_llm_output_to_the_rdb_cell_format(self) -> None:
        class FakeCompletionClient:
            def __init__(self) -> None:
                self.messages = []

            def complete(self, model, messages):
                self.messages = messages
                return """```json
["Row Header: IBM Market Capitalization | Column Header: LTM", "Sheet: Key Statistics | Row Header: IBM Total Enterprise Value | Column Header: LTM | Cell Value: ?"]
```"""

        client = FakeCompletionClient()
        module = DecomposerModule(client)
        result = module.run(
            {
                "query_context": sample_query_context(
                    "QUERY-DECOMPOSER",
                    "IBM의 LTM 기준 시가총액과 TEV는?",
                ),
                "system_prompt": "custom system",
                "user_prompt_template": "Question: {question}",
            }
        )

        expected_variants = {
            "Sheet: ? | Row Header: IBM Market Capitalization | Column Header: LTM | Cell Value: ?",
            "Sheet: ? | Row Header: IBM Market Cap | Column Header: FY0 | Cell Value: ?",
            "Sheet: ? | Row Header: IBM Equity Market Value | Column Header: 2025-12-31 | Cell Value: ?",
            "Sheet: Key_Stats | Row Header: IBM Total Enterprise Value | Column Header: LTM | Cell Value: ?",
            "Sheet: Key_Stats | Row Header: IBM Enterprise Value | Column Header: FY2025 | Cell Value: ?",
            "Sheet: Key_Stats | Row Header: IBM TEV | Column Header: 2025-12-31 | Cell Value: ?",
        }
        self.assertTrue(
            expected_variants.issubset(set(result["subqueries"])),
            result["subqueries"],
        )
        self.assertEqual(
            set(result),
            {"query_context", "subqueries"},
        )
        self.assertEqual([message["role"] for message in client.messages], ["system", "user"])
        self.assertIn("custom system", client.messages[0]["content"])
        self.assertIn("IBM의 LTM 기준", client.messages[1]["content"])

    def test_default_decomposer_prompt_has_no_count_cap_or_acronym_conflict(self) -> None:
        class FakeCompletionClient:
            def __init__(self) -> None:
                self.messages = []

            def complete(self, model, messages):
                self.messages = messages
                return '["Row Header: Total Enterprise Value | Column Header: LTM"]'

        client = FakeCompletionClient()
        DecomposerModule(client).run(
            {"query_context": sample_query_context("QUERY-PROMPT", "LTM TEV는?")}
        )
        prompt = "\n".join(message["content"] for message in client.messages)

        self.assertNotIn("2-4", prompt)
        self.assertIn("no maximum number", prompt)
        self.assertIn("Total Enterprise Value, Enterprise Value, and TEV", prompt)
        self.assertIn("LTM, FY0, FY2025, and 2025-12-31", prompt)

    def test_decomposer_cache_identity_uses_effective_model_defaults(self) -> None:
        module = DecomposerModule(StubCompletionClient())
        query_input = {"query_context": sample_query_context("QUERY-CACHE", "동일 질문")}
        implicit_luna = module.cache_payload(query_input)
        explicit_luna = module.cache_payload(
            {**query_input, "model": "gpt-5.6-luna"}
        )
        terra = module.cache_payload(
            {**query_input, "model": "gpt-5.6-terra"}
        )

        self.assertEqual(
            ResultCache.key("decomposer@6", implicit_luna),
            ResultCache.key("decomposer@6", explicit_luna),
        )
        self.assertNotEqual(
            ResultCache.key("decomposer@6", implicit_luna),
            ResultCache.key("decomposer@6", terra),
        )

    def test_decomposer_propagates_llm_failure_without_fallback_output(self) -> None:
        class FailedCompletionClient:
            def complete(self, model, messages):
                raise ChatCompletionError("provider unavailable")

        with self.assertRaisesRegex(ModuleExecutionError, "provider unavailable"):
            DecomposerModule(FailedCompletionClient()).run(
                {
                    "query_context": sample_query_context(
                        "QUERY-FAILURE",
                        "폴백을 만들면 안 되는 질문",
                    )
                }
            )

    def test_invalid_module_input_returns_validation_error(self) -> None:
        response = self.client.post(
            "/api/modules/embedder/execute",
            json={"input": {}},
        )
        self.assertEqual(response.status_code, 422)

    def test_unknown_dto_field_is_rejected(self) -> None:
        response = self.client.post(
            "/api/modules/json_transformer/execute",
            json={
                "input": {"any_json": {"source": 7}},
                "config": {"mapping_typo": {}},
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_legacy_fixed_pipeline_endpoint_is_not_exposed(self) -> None:
        self.assertEqual(self.client.get("/api/pipeline/Q001").status_code, 404)


class SpreadsheetModuleTests(unittest.TestCase):
    class FullSheetExtractor:
        def detect(self, image_path: Path):
            with Image.open(image_path) as image:
                return [(0, 0, image.width, image.height)]

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.processed_dir = self.root / "data" / "processed"
        self.artifact_dir = self.root / "data" / "artifacts" / "spreadsheets"
        self.processed_dir.mkdir(parents=True)
        self.workbook_path = self.processed_dir / "sample.xlsx"

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Key Stats"
        sheet.append(["Metric", "LTM", "FY0"])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
        sheet.append(["Revenue", 100, 90])
        sheet.append(["EBITDA", 30, 25])
        sheet.append(["TEV", 500, 450])
        workbook.save(self.workbook_path)
        workbook.close()
        self.catalog = WorkbookCatalog(self.processed_dir)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_spreadsheet_artifact_api_serves_rendered_sheet_image(self) -> None:
        workbook_hash = "a" * 64
        image_path = (
            self.artifact_dir
            / workbook_hash[:16]
            / "rendered"
            / "Key_Stats.png"
        )
        image_path.parent.mkdir(parents=True)
        Image.new("RGB", (12, 8), "white").save(image_path)

        application = FastAPI()
        application.include_router(
            create_spreadsheet_artifact_router(self.artifact_dir),
            prefix="/api",
        )
        client = TestClient(application)

        response = client.get(
            f"/api/spreadsheet-artifacts/{workbook_hash}/sheets/Key_Stats"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(
            client.get(
                "/api/spreadsheet-artifacts/not-a-hash/sheets/Key_Stats"
            ).status_code,
            422,
        )

    def test_selector_docling_and_openpyxl_modules_chain_without_hitl(self) -> None:
        selector = ProcessedFileSelectorModule(catalog=self.catalog)
        selector_contract = selector.contract()
        self.assertEqual(
            selector_contract["input_schema"]["properties"]["file_name"]["enum"],
            ["sample.xlsx"],
        )
        selection = selector.run({"file_name": "sample.xlsx"})
        self.assertEqual(selection["sheet_names"], ["Key Stats"])

        docling = DoclingTableDetectorModule(
            catalog=self.catalog,
            extractor=self.FullSheetExtractor(),
            artifact_dir=self.artifact_dir,
        )
        detected = docling.run(selection)
        self.assertNotIn("sheets", detected)
        self.assertEqual(len(detected["tables"]), 1)
        table = detected["tables"][0]
        self.assertEqual(table["sheet_name"], "Key Stats")
        self.assertEqual(table["excel_range"], "A1:C4")
        self.assertEqual(
            table["cell_bounds"],
            {"min_row": 1, "max_row": 4, "min_column": 1, "max_column": 3},
        )
        self.assertEqual(len(table["bbox_px"]), 4)
        self.assertTrue((self.artifact_dir / selection["workbook_hash"][:16] / "rendered" / "Key_Stats.png").is_file())

        classified = OpenpyxlRegionDetectorModule(catalog=self.catalog).run(detected)
        self.assertNotIn("sheets", classified)
        self.assertEqual(classified["tables"][0]["sheet_name"], "Key Stats")
        regions = classified["tables"][0]["regions"]
        self.assertEqual(
            {region["type"] for region in regions},
            {"column_header", "row_header", "data"},
        )
        self.assertNotIn("is_approved", classified)
        self.assertNotIn("review", classified)

        serialized = CellTextSerializerModule(catalog=self.catalog).run(classified)
        self.assertEqual(set(serialized), {"file_name", "workbook_hash", "items"})
        self.assertEqual(len(serialized["items"]), 12)
        header_only = serialized["items"][0]
        with_value = serialized["items"][1]
        self.assertEqual(header_only["cell_id"], "KS Cell B2")
        self.assertEqual(header_only["sheet_name"], "Key_Stats")
        self.assertEqual(header_only["row_header"], ["Revenue"])
        self.assertEqual(header_only["column_header"], ["LTM"])
        self.assertEqual(header_only["variant"], "header_only")
        self.assertEqual(
            header_only["text"],
            "Sheet: Key_Stats | Row Header: Revenue | Column Header: LTM | Cell Value: ?",
        )
        self.assertEqual(with_value["variant"], "header_with_value")
        self.assertEqual(
            with_value["text"],
            "Sheet: Key_Stats | Row Header: Revenue | Column Header: LTM | Cell Value: 100",
        )

    def test_exhaustive_serializer_embeds_every_left_above_combination(self) -> None:
        workbook_path = self.processed_dir / "cartesian.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Key Stats"
        sheet.append(["Metric", "FY2024", "FY2025", "HIDDEN_COLUMN_SECRET"])
        sheet.append(["Revenue", 10, 20, "HIDDEN_COLUMN_SECRET"])
        sheet.append(["HIDDEN_ROW_SECRET", 30, 40, "HIDDEN_ROW_SECRET"])
        sheet.row_dimensions[3].hidden = True
        sheet.column_dimensions["D"].hidden = True
        workbook.save(workbook_path)
        workbook.close()

        selection = ProcessedFileSelectorModule(catalog=self.catalog).run(
            {"file_name": workbook_path.name}
        )
        serialized = ExhaustiveCellTextSerializerModule(catalog=self.catalog).run(
            selection
        )

        self.assertEqual(len(serialized["items"]), 8)
        serialized_text = str(serialized)
        self.assertNotIn("HIDDEN_ROW_SECRET", serialized_text)
        self.assertNotIn("HIDDEN_COLUMN_SECRET", serialized_text)
        c2_items = [
            item for item in serialized["items"] if item["cell_coord"] == "C2"
        ]
        self.assertEqual(len(c2_items), 2)
        self.assertEqual(
            {item["text"] for item in c2_items},
            {
                "Sheet: Key_Stats | Row Header: Revenue | Column Header: FY2025 | Cell Value: ?",
                "Sheet: Key_Stats | Row Header: 10 | Column Header: FY2025 | Cell Value: ?",
            },
        )
        self.assertEqual({item["cell_value"] for item in c2_items}, {"20"})

        embedding_store = EmbeddingArtifactStore(self.root / "embeddings")
        index_store = VectorIndexStore(self.root / "indexes")
        embedded = CellTextEmbedderModule(
            StubEmbeddingEncoder(),
            embedding_store,
        ).run(serialized)
        indexed = VectorIndexWriterModule(
            embedding_store,
            index_store,
        ).run(embedded)
        self.assertEqual(indexed["document_count"], 8)
        self.assertEqual(indexed["dimension"], 2)

        with self.assertRaisesRegex(ModuleExecutionError, "안전 한도"):
            ExhaustiveCellTextSerializerModule(catalog=self.catalog).run(
                {**selection, "max_documents": 7}
            )

    def test_hidden_axes_and_sheets_never_enter_spreadsheet_outputs(self) -> None:
        workbook_path = self.processed_dir / "hidden-content.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Visible"
        sheet.append(["Metric", "LTM", "Hidden Period", "FY0"])
        sheet.append(["Revenue", 100, "HIDDEN_COLUMN_SECRET", 90])
        sheet.append(["HIDDEN_ROW_SECRET", 999, 999, 999])
        sheet.append(["EBITDA", 30, "HIDDEN_COLUMN_SECRET", 25])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
        sheet.row_dimensions[3].hidden = True
        sheet.column_dimensions["C"].hidden = True
        hidden_sheet = workbook.create_sheet("Hidden Sheet")
        hidden_sheet["A1"] = "HIDDEN_SHEET_SECRET"
        hidden_sheet.sheet_state = "hidden"
        workbook.save(workbook_path)
        workbook.close()

        selection = ProcessedFileSelectorModule(catalog=self.catalog).run(
            {"file_name": workbook_path.name}
        )
        self.assertEqual(selection["sheet_names"], ["Visible"])

        detected = DoclingTableDetectorModule(
            catalog=self.catalog,
            extractor=self.FullSheetExtractor(),
            artifact_dir=self.artifact_dir,
        ).run(selection)
        self.assertEqual(detected["tables"][0]["excel_range"], "A1:D4")

        classified = OpenpyxlRegionDetectorModule(catalog=self.catalog).run(detected)
        serialized = CellTextSerializerModule(catalog=self.catalog).run(classified)
        serialized_text = str(serialized)
        self.assertNotIn("HIDDEN_ROW_SECRET", serialized_text)
        self.assertNotIn("HIDDEN_COLUMN_SECRET", serialized_text)
        self.assertNotIn("HIDDEN_SHEET_SECRET", serialized_text)
        self.assertEqual(
            {item["cell_coord"] for item in serialized["items"]},
            {"B2", "D2", "B4", "D4"},
        )

        class CapturingVisionClient:
            def __init__(self):
                self.prompt = ""
                self.system_prompt = ""

            def complete_structured(
                self,
                model,
                system_prompt,
                user_prompt,
                image_path,
                json_schema,
                context_window,
                timeout_seconds,
            ):
                self.system_prompt = system_prompt
                self.prompt = user_prompt
                return (
                    '{"sheet_name":"Visible","tables":[{'
                    '"excel_range":"A1:D4","title_range":null,'
                    '"column_header_range":"A1:D1","row_header_range":"A2:A4",'
                    '"data_range":"B2:D4"}]}'
                )

        vision_client = CapturingVisionClient()
        vlm_output = LocalVlmStructureDetectorModule(
            vision_client,
            catalog=self.catalog,
            artifact_dir=self.artifact_dir,
        ).run(selection)
        self.assertNotIn("HIDDEN_ROW_SECRET", vision_client.prompt)
        self.assertNotIn("HIDDEN_COLUMN_SECRET", vision_client.prompt)
        self.assertNotIn("Hidden Period", vision_client.prompt)
        self.assertIn(
            "A text-typed cell is not automatically a header",
            vision_client.system_prompt,
        )
        vlm_serialized = CellTextSerializerModule(catalog=self.catalog).run(vlm_output)
        self.assertEqual(
            {item["cell_coord"] for item in vlm_serialized["items"]},
            {"B2", "D2", "B4", "D4"},
        )

        class CapturingBoundaryClient:
            def __init__(self):
                self.messages = []

            def complete_structured(self, model, messages, schema_name, json_schema):
                self.messages.extend(messages)
                return (
                    '{"decisions":[{"region_id":"Visible:table_1",'
                    '"title_row_end":null,"data_start_row":2,'
                    '"index_column_count":1}]}'
                )

        boundary_client = CapturingBoundaryClient()
        bfs_output = BfsLlmStructureDetectorModule(
            boundary_client,
            catalog=self.catalog,
            artifact_dir=self.artifact_dir,
        ).run(selection)
        boundary_prompt = str(boundary_client.messages)
        self.assertNotIn("HIDDEN_ROW_SECRET", boundary_prompt)
        self.assertNotIn("HIDDEN_COLUMN_SECRET", boundary_prompt)
        self.assertIn("Missing-value and status literals", boundary_prompt)
        self.assertIn("`NA`", boundary_prompt)
        bfs_serialized = CellTextSerializerModule(catalog=self.catalog).run(bfs_output)
        self.assertEqual(
            {item["cell_coord"] for item in bfs_serialized["items"]},
            {"B2", "D2", "B4", "D4"},
        )

    def test_zero_sized_and_grouped_axes_are_hidden_from_geometry(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet["A1"] = "visible"
        sheet["B2"] = "zero-sized"
        sheet["D3"] = "grouped"
        sheet.row_dimensions[2].height = 0
        sheet.column_dimensions["B"].width = 0
        sheet.column_dimensions.group("D", "E", hidden=True)

        visibility = WorksheetVisibility.from_worksheet(sheet)
        self.assertTrue(visibility.row_hidden(2))
        self.assertTrue(visibility.column_hidden(2))
        self.assertTrue(visibility.column_hidden(4))
        self.assertTrue(visibility.column_hidden(5))

        layout = compute_sheet_layout(sheet, 5, 5)
        self.assertEqual(layout.row_heights[1], 0)
        self.assertEqual(layout.column_widths[1], 0)
        self.assertEqual(layout.column_widths[3], 0)
        bounds = bbox_to_cell_bounds(
            (0, 0, layout.width, layout.height),
            layout,
        )
        self.assertNotIn(bounds.min_row, visibility.hidden_rows)
        self.assertNotIn(bounds.max_row, visibility.hidden_rows)
        self.assertNotIn(bounds.min_column, visibility.hidden_columns)
        self.assertNotIn(bounds.max_column, visibility.hidden_columns)
        workbook.close()

    def test_local_vlm_detector_uses_typed_image_and_coordinate_context(self) -> None:
        class VisionClient:
            def __init__(self):
                self.calls = []

            def complete_structured(
                self,
                model,
                system_prompt,
                user_prompt,
                image_path,
                json_schema,
                context_window,
                timeout_seconds,
            ):
                self.calls.append(
                    {
                        "model": model,
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "image_path": image_path,
                        "json_schema": json_schema,
                        "context_window": context_window,
                        "timeout_seconds": timeout_seconds,
                    }
                )
                return (
                    '{"sheet_name":"Key Stats","tables":[{'
                    '"excel_range":"A1:C4","title_range":null,'
                    '"column_header_range":"A1:C1","row_header_range":"A2:A4",'
                    '"data_range":"B2:C4"}]}'
                )

        client = VisionClient()
        selection = ProcessedFileSelectorModule(catalog=self.catalog).run(
            {"file_name": "sample.xlsx"}
        )
        structured = LocalVlmStructureDetectorModule(
            client,
            catalog=self.catalog,
            artifact_dir=self.artifact_dir,
        ).run(selection)

        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["model"], "qwen3-vl:4b-instruct")
        self.assertIn('"cell_tuple":["excel_coord"', call["user_prompt"])
        self.assertIn('A1', call["user_prompt"])
        self.assertIn('"text"', call["user_prompt"])
        self.assertIn('"number"', call["user_prompt"])
        self.assertIn("Ordinary descriptive text is strong structural evidence", call["system_prompt"])
        self.assertIn("`NA`", call["system_prompt"])
        self.assertIn("Keep them inside data_range", call["system_prompt"])
        self.assertTrue(call["image_path"].is_file())
        self.assertIn("typed", call["image_path"].parts)
        table = structured["tables"][0]
        self.assertEqual(
            {region["type"] for region in table["regions"]},
            {"column_header", "row_header", "data"},
        )
        self.assertEqual(table["regions"][-1]["parent_ids"], [
            "table_1_column_header",
            "table_1_row_header",
        ])
        serialized = CellTextSerializerModule(catalog=self.catalog).run(structured)
        self.assertEqual(len(serialized["items"]), 12)

    def test_exhaustive_tiles_cover_every_visible_cell_and_no_hidden_cell(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet["E5"] = "extent"
        sheet.row_dimensions[2].hidden = True
        sheet.column_dimensions["B"].hidden = True
        layout = compute_sheet_layout(sheet, 10, 10)

        tiles = build_exhaustive_tiles(
            layout,
            tile_rows=2,
            tile_columns=2,
            row_overlap=1,
            column_overlap=1,
        )
        covered = {
            (row, column)
            for tile in tiles
            for row in tile.visible_rows
            for column in tile.visible_columns
        }
        expected = {
            (row, column)
            for row in (1, 3, 4, 5)
            for column in (1, 3, 4, 5)
        }
        self.assertEqual(covered, expected)
        self.assertTrue(all(2 not in tile.visible_rows for tile in tiles))
        self.assertTrue(all(2 not in tile.visible_columns for tile in tiles))
        workbook.close()

    def test_luna_vlm_detector_analyzes_each_whole_sheet_without_tiles(self) -> None:
        class VisionClient:
            def __init__(self):
                self.calls = []

            def complete_structured(self, **kwargs):
                self.calls.append(kwargs)
                return (
                    '{"tables":[{'
                    '"excel_range":"A1:C4","title_range":null,'
                    '"column_header_range":"A1:C1","row_header_range":"A2:A4",'
                    '"data_range":"A2:C4"}]}'
                )

        client = VisionClient()
        selection = ProcessedFileSelectorModule(catalog=self.catalog).run(
            {"file_name": "sample.xlsx"}
        )
        structured = LunaVlmStructureDetectorModule(
            client,
            catalog=self.catalog,
            artifact_dir=self.artifact_dir,
        ).run({
            **selection,
            # Legacy tiling settings are accepted and discarded when old workflows run.
            "tile_rows": 72,
            "tile_columns": 24,
            "row_overlap": 8,
            "column_overlap": 2,
            "max_concurrency": 2,
        })

        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["model"], "gpt-5.6-luna")
        self.assertEqual(call["reasoning_effort"], "low")
        self.assertIn('"sheet_range":"A1:C4"', call["user_prompt"])
        self.assertIn('"cell_tuple":["excel_coord"', call["user_prompt"])
        self.assertNotIn("tile", call["user_prompt"].lower())
        self.assertIn("Ordinary descriptive text is strong structural evidence", call["system_prompt"])
        self.assertIn("`N/A`", call["system_prompt"])
        self.assertIn("Keep them inside data_range", call["system_prompt"])
        self.assertNotIn("candidate", call["user_prompt"].lower())
        self.assertTrue(call["image_path"].is_file())
        self.assertIn("typed", call["image_path"].parts)
        self.assertEqual(len(structured["tables"]), 1)
        self.assertEqual(structured["tables"][0]["excel_range"], "A1:C4")
        self.assertEqual(
            {region["type"] for region in structured["tables"][0]["regions"]},
            {"column_header", "row_header", "data"},
        )
        regions = {
            region["type"]: region["excel_range"]
            for region in structured["tables"][0]["regions"]
        }
        self.assertEqual(regions["row_header"], "A2:A4")
        self.assertEqual(regions["data"], "B2:C4")
        serialized = CellTextSerializerModule(catalog=self.catalog).run(structured)
        self.assertEqual(len(serialized["items"]), 12)

    def test_bfs_llm_detector_builds_title_regions_and_hierarchical_headers(self) -> None:
        workbook_path = self.processed_dir / "hierarchical.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Summary"
        sheet.merge_cells("A1:D1")
        sheet["A1"] = "SUMMARY RATIOS"
        sheet["A2"] = "Profitability"
        sheet.merge_cells("B2:D2")
        sheet["B2"] = "Fiscal Year Ending"
        sheet.append(["Metric", "2024-12-31", "2025-12-31", "2026-12-31"])
        sheet.append(["Return on Assets", 0.068, 0.071, 0.075])
        sheet["A1"].font = Font(bold=True, size=14, color="FFFFFF")
        sheet["A1"].fill = PatternFill(fill_type="solid", fgColor="44546A")
        workbook.save(workbook_path)
        workbook.close()

        class BoundaryClient:
            def __init__(self):
                self.messages = []

            def complete_structured(self, model, messages, schema_name, json_schema):
                self.messages.extend(messages)
                self.schema_name = schema_name
                self.json_schema = json_schema
                return (
                    '{"decisions":[{"region_id":"Summary:table_1",'
                    '"title_row_end":1,"data_start_row":4,'
                    '"index_column_count":1}]}'
                )

        client = BoundaryClient()
        selector = ProcessedFileSelectorModule(catalog=self.catalog)
        selection = selector.run({"file_name": "hierarchical.xlsx"})
        detector = BfsLlmStructureDetectorModule(
            client,
            catalog=self.catalog,
            artifact_dir=self.artifact_dir,
        )
        structured = detector.run(selection)

        self.assertEqual(len(structured["tables"]), 1)
        table = structured["tables"][0]
        self.assertEqual(table["excel_range"], "A1:D4")
        self.assertEqual(
            {region["type"] for region in table["regions"]},
            {"title", "column_header", "row_header", "data"},
        )
        fiscal_year = next(
            node for node in table["header_tree"] if node["name"] == "Fiscal Year Ending"
        )
        self.assertEqual(
            [child["name"] for child in fiscal_year["children"]],
            ["2024-12-31", "2025-12-31", "2026-12-31"],
        )
        self.assertIn('"is_merged":true', client.messages[-1]["content"])
        self.assertEqual(client.schema_name, "excel_table_boundaries")
        self.assertEqual(client.json_schema["additionalProperties"], False)

        serialized = CellTextSerializerModule(catalog=self.catalog).run(structured)
        self.assertEqual(len(serialized["items"]), 54)
        first = serialized["items"][0]
        self.assertEqual(first["row_header"], ["SUMMARY RATIOS", "Return on Assets"])
        self.assertEqual(
            first["column_header"],
            ["Fiscal Year Ending", "2024-12-31"],
        )
        self.assertTrue(
            (
                self.artifact_dir
                / selection["workbook_hash"][:16]
                / "rendered"
                / "Summary.png"
            ).is_file()
        )


class WorkflowExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.repository = AnswerCacheRepository()
        self.registry = ModuleRegistry(
            self.repository,
            StubCompletionClient(),
            StubEmbeddingEncoder(),
            EmbeddingArtifactStore(root / "embeddings"),
            VectorIndexStore(root / "vector-indexes"),
        )
        self.workflow_store = WorkflowStore(root / "workflows")
        self.run_store = RunStore(root / "runs")
        self.cache = ResultCache(root / "cache")
        self.executor = WorkflowExecutor(
            self.registry,
            self.run_store,
            self.cache,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def graph() -> WorkflowGraph:
        module_types = [
            ("query", "query_input"),
            ("documents", "json_inspector"),
            ("document_embed", "cell_text_embedder"),
            ("vector_index", "vector_index_writer"),
            ("decompose", "decomposer"),
            ("embed", "embedder"),
            ("bm25", "bm25_retriever"),
            ("dense", "dense_retriever"),
            ("rrf", "rrf_fusion"),
            ("context", "context"),
            ("reader", "reader"),
            ("transform", "json_transformer"),
            ("inspect", "json_inspector"),
        ]
        return WorkflowGraph(
            nodes=[
                WorkflowNode(
                    id=node_id,
                    module_type=module_type,
                    position=CanvasPosition(x=index * 120, y=0),
                    config=(
                        {"mappings": {"question_id": "id"}}
                        if node_id == "transform"
                        else {"threshold": 0.99}
                        if node_id == "query"
                        else {}
                    ),
                    values=(
                        {"query": "저장 후 복원할 사용자 질문"}
                        if module_type == "query_input"
                        else {}
                    ),
                    ui=(
                        {
                            "width": 640,
                            "execution_stopped": True,
                            "column_widths": {
                                "subquery": 320,
                                "embedding": 560,
                            },
                        }
                        if node_id == "inspect"
                        else {}
                    ),
                )
                for index, (node_id, module_type) in enumerate(module_types)
            ],
            edges=[
                WorkflowEdge(
                    id="e1",
                    source="query",
                    target="decompose",
                    source_branch="generated",
                    target_input="query_context",
                ),
                WorkflowEdge(id="e2", source="decompose", target="embed"),
                WorkflowEdge(
                    id="e3",
                    source="decompose",
                    target="bm25",
                    target_input="query_input",
                ),
                WorkflowEdge(
                    id="e4",
                    source="embed",
                    target="dense",
                    target_input="query_input",
                ),
                WorkflowEdge(
                    id="e11",
                    source="documents",
                    target="bm25",
                    target_input="document_input",
                ),
                WorkflowEdge(
                    id="e12",
                    source="documents",
                    target="document_embed",
                ),
                WorkflowEdge(
                    id="e13",
                    source="document_embed",
                    target="vector_index",
                ),
                WorkflowEdge(
                    id="e16",
                    source="vector_index",
                    target="dense",
                    target_input="index_input",
                ),
                WorkflowEdge(
                    id="e5",
                    source="bm25",
                    target="rrf",
                    target_input="bm25_result",
                ),
                WorkflowEdge(
                    id="e6",
                    source="dense",
                    target="rrf",
                    target_input="dense_result",
                ),
                WorkflowEdge(
                    id="e7",
                    source="rrf",
                    target="context",
                    target_input="retrieval_json",
                ),
                WorkflowEdge(
                    id="e14",
                    source="documents",
                    target="context",
                    target_input="document_input",
                ),
                WorkflowEdge(
                    id="e8",
                    source="context",
                    target="reader",
                    target_input="context_json",
                ),
                WorkflowEdge(id="e9", source="decompose", target="transform"),
                WorkflowEdge(id="e10", source="transform", target="inspect"),
            ],
        )

    def save_workflow(self):
        return self.workflow_store.save(
            "test-flow",
            WorkflowSaveRequest(name="Test Flow", graph=self.graph()),
        )

    def runtime_request(self) -> WorkflowExecutionRequest:
        return WorkflowExecutionRequest(
            inputs={
                "query": {"query": "질문 Q001"},
                "documents": {"input": sample_cell_documents()},
            }
        )

    def test_workflow_is_saved_as_editable_json_and_reloads(self) -> None:
        saved = self.save_workflow()
        raw_path = Path(self.temporary_directory.name) / "workflows" / "test-flow.json"
        raw = raw_path.read_text(encoding="utf-8")

        self.assertIn('"schema_version": 1', raw)
        self.assertIn('"module_type": "query_input"', raw)
        reloaded = WorkflowStore(raw_path.parent).load("test-flow")
        self.assertEqual(reloaded.graph, saved.graph)
        query_node = next(
            node for node in reloaded.graph.nodes if node.module_type == "query_input"
        )
        inspector_node = next(
            node for node in reloaded.graph.nodes if node.id == "inspect"
        )
        self.assertEqual(query_node.values["query"], "저장 후 복원할 사용자 질문")
        self.assertEqual(inspector_node.ui.width, 640)
        self.assertTrue(inspector_node.ui.execution_stopped)
        self.assertEqual(
            inspector_node.ui.column_widths,
            {"subquery": 320, "embedding": 560},
        )
        self.assertEqual(
            {
                edge.target_input
                for edge in reloaded.graph.edges
                if edge.target == "rrf"
            },
            {"bm25_result", "dense_result"},
        )

    def test_active_workflow_falls_back_to_default_template(self) -> None:
        default = self.workflow_store.save(
            "default",
            WorkflowSaveRequest(name="Default Template", graph=self.graph()),
        )

        active = self.workflow_store.load("workflow")

        self.assertEqual(active.id, "workflow")
        self.assertEqual(active.name, default.name)
        self.assertEqual(active.graph, default.graph)
        self.assertFalse(
            (
                Path(self.temporary_directory.name)
                / "workflows"
                / "workflow.json"
            ).exists()
        )

        saved_active = self.workflow_store.save(
            "workflow",
            WorkflowSaveRequest(name="Local Workflow", graph=self.graph()),
        )
        self.assertEqual(self.workflow_store.load("workflow"), saved_active)

    def test_missing_non_active_workflow_does_not_use_default_template(self) -> None:
        self.workflow_store.save(
            "default",
            WorkflowSaveRequest(name="Default Template", graph=self.graph()),
        )

        with self.assertRaises(FileNotFoundError):
            self.workflow_store.load("missing-workflow")

    def test_run_list_reads_a_compact_summary_without_changing_resume_state(self) -> None:
        workflow = self.save_workflow()
        run = self.executor.create_run(workflow, self.runtime_request())
        vector = [float(index) for index in range(1024)]
        run.nodes["query"].output = {"embedding": vector}
        self.run_store.save(run)

        summary_path = (
            Path(self.temporary_directory.name)
            / "runs"
            / f"{run.id}.summary.json"
        )
        self.assertTrue(summary_path.is_file())
        listed_output = self.run_store.list()[0].nodes["query"].output
        self.assertEqual(listed_output["embedding"]["_summary"], "numeric vector")
        self.assertEqual(listed_output["embedding"]["length"], len(vector))
        self.assertEqual(self.run_store.load(run.id).nodes["query"].output["embedding"], vector)

    def test_graph_fixture_matches_registered_modules(self) -> None:
        graph = self.graph()
        batches = self.executor.validate_graph(graph)

        registered = {definition["type"] for definition in self.registry.definitions()}
        self.assertTrue({node.module_type for node in graph.nodes}.issubset(registered))
        self.assertEqual(sum(len(batch) for batch in batches), len(graph.nodes))

    def test_saved_default_workflow_reproduces_the_modular_dag_contract(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        workflow = WorkflowStore(project_root / "data" / "workflows").load("default")
        batches = self.executor.validate_graph(workflow.graph)
        module_type_by_id = {
            node.id: node.module_type for node in workflow.graph.nodes
        }
        prebuilt_node = next(
            node
            for node in workflow.graph.nodes
            if node.module_type == "prebuilt_index_loader"
        )
        self.assertNotIn("file_name", prebuilt_node.config)
        self.assertIn("file_name", prebuilt_node.values)
        connections = {
            (
                module_type_by_id[edge.source],
                module_type_by_id[edge.target],
                edge.target_input,
            )
            for edge in workflow.graph.edges
        }

        expected_connections = {
            ("query_input", "decomposer", "query_context"),
            ("prebuilt_index_loader", "bm25_retriever", "document_input"),
            ("prebuilt_index_loader", "dense_retriever", "index_input"),
            ("prebuilt_index_loader", "context", "document_input"),
            ("decomposer", "json_inspector", "input"),
            ("json_inspector", "embedder", "input"),
            ("json_inspector", "bm25_retriever", "query_input"),
            ("embedder", "dense_retriever", "query_input"),
            ("bm25_retriever", "rrf_fusion", "bm25_result"),
            ("dense_retriever", "rrf_fusion", "dense_result"),
            ("rrf_fusion", "context", "retrieval_json"),
            ("context", "reader", "context_json"),
            ("reader", "json_inspector", "input"),
        }
        self.assertTrue(batches)
        self.assertTrue(expected_connections.issubset(connections))
        self.assertFalse(
            any(
                source == "query_input" and target == "reader"
                for source, target, _ in connections
            )
        )

    def test_all_saved_workflows_use_valid_input_and_config_layers(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        workflow_dir = project_root / "data" / "workflows"
        workflow_store = WorkflowStore(workflow_dir)

        for path in sorted(workflow_dir.glob("*.json")):
            with self.subTest(workflow=path.name):
                workflow = workflow_store.load(path.stem)
                batches = self.executor.validate_graph(workflow.graph)
                self.assertEqual(
                    sum(len(batch) for batch in batches),
                    len(workflow.graph.nodes),
                )

    def test_runtime_input_cannot_override_node_config(self) -> None:
        workflow = self.save_workflow()
        with self.assertRaisesRegex(DagExecutionError, "node.config"):
            self.executor.create_run(
                workflow,
                WorkflowExecutionRequest(
                    inputs={"query": {"query": "질문", "threshold": 0.1}}
                ),
            )

    def test_rrf_is_skipped_when_one_required_input_is_missing(self) -> None:
        graph = self.graph()
        graph.edges = [edge for edge in graph.edges if edge.id != "e6"]
        workflow = self.workflow_store.save(
            "missing-rrf-input",
            WorkflowSaveRequest(name="Missing RRF Input", graph=graph),
        )
        run = self.executor.create_run(workflow, self.runtime_request())
        completed = self.executor.execute_all(run.id)

        self.assertEqual(completed.nodes["rrf"].status, "skipped")
        self.assertIn("dense_result", completed.nodes["rrf"].skip_reason)

    def test_batches_persist_outputs_and_feed_the_next_batch(self) -> None:
        workflow = self.save_workflow()
        run = self.executor.create_run(workflow, self.runtime_request())
        self.assertEqual(
            [batch.node_ids for batch in run.batches],
            [
                ["query", "documents"],
                ["decompose", "document_embed"],
                ["embed", "bm25", "transform", "vector_index"],
                ["inspect", "dense"],
                ["rrf"],
                ["context"],
                ["reader"],
            ],
        )

        after_query = self.executor.execute_next_batch(run.id)
        query_output = after_query.nodes["query"].output
        self.assertEqual(after_query.nodes["query"].status, "succeeded")
        self.assertIsNotNone(query_output)
        self.assertEqual(
            after_query.nodes["query"].input_payload,
            {"query": "질문 Q001"},
        )
        self.assertEqual(
            after_query.nodes["query"].config_payload,
            {"threshold": 0.99},
        )

        after_decompose = self.executor.execute_next_batch(run.id)
        self.assertEqual(
            after_decompose.nodes["decompose"].input_payload["query_context"],
            query_output["query_context"],
        )
        persisted = self.run_store.load(run.id)
        self.assertEqual(
            persisted.nodes["decompose"].output,
            after_decompose.nodes["decompose"].output,
        )

    def test_single_node_execution_does_not_run_same_batch_siblings(self) -> None:
        workflow = self.save_workflow()
        run = self.executor.create_run(workflow, self.runtime_request())

        with self.assertRaisesRegex(DagExecutionError, "활성화된 분기 출력"):
            self.executor.execute_node(run.id, "decompose")

        after_query = self.executor.execute_node(run.id, "query")

        self.assertEqual(after_query.nodes["query"].status, "succeeded")
        self.assertEqual(after_query.nodes["documents"].status, "pending")
        self.assertEqual(after_query.batches[0].status, "pending")
        self.assertEqual(after_query.status, "queued")

        after_documents = self.executor.execute_node(run.id, "documents")
        self.assertEqual(after_documents.nodes["query"].status, "succeeded")
        self.assertEqual(after_documents.nodes["documents"].status, "succeeded")
        self.assertEqual(after_documents.batches[0].status, "completed")

        after_decompose = self.executor.execute_node(run.id, "decompose")
        self.assertEqual(after_decompose.nodes["decompose"].status, "succeeded")
        self.assertEqual(after_decompose.nodes["document_embed"].status, "pending")
        self.assertEqual(after_decompose.batches[1].status, "pending")

    def test_cancel_terminates_active_module_and_restores_pending_state(self) -> None:
        workflow = self.save_workflow()
        run = self.executor.create_run(workflow, self.runtime_request())
        worker = BlockingModuleWorker()
        executor = WorkflowExecutor(
            self.registry,
            self.run_store,
            self.cache,
            module_worker=worker,
        )
        errors = []

        def execute_query():
            try:
                executor.execute_node(run.id, "query")
            except Exception as error:
                errors.append(error)

        execution_thread = Thread(target=execute_query)
        execution_thread.start()
        self.assertTrue(worker.started.wait(timeout=1))

        started_at = monotonic()
        cancelled = executor.cancel_run(run.id)
        elapsed = monotonic() - started_at
        execution_thread.join(timeout=1)

        self.assertFalse(execution_thread.is_alive())
        self.assertLess(elapsed, 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], DagExecutionCancelled)
        self.assertEqual(cancelled.status, "queued")
        self.assertEqual(cancelled.nodes["query"].status, "pending")
        self.assertIsNone(cancelled.nodes["query"].output)

    def test_cache_clear_terminates_active_module_before_removing_runs(self) -> None:
        workflow = self.save_workflow()
        run = self.executor.create_run(workflow, self.runtime_request())
        worker = BlockingModuleWorker()
        executor = WorkflowExecutor(
            self.registry,
            self.run_store,
            self.cache,
            module_worker=worker,
        )
        errors = []

        def execute_query():
            try:
                executor.execute_node(run.id, "query")
            except Exception as error:
                errors.append(error)

        execution_thread = Thread(target=execute_query)
        execution_thread.start()
        self.assertTrue(worker.started.wait(timeout=1))

        started_at = monotonic()
        result = executor.clear_runtime_cache()
        elapsed = monotonic() - started_at
        execution_thread.join(timeout=1)

        self.assertFalse(execution_thread.is_alive())
        self.assertLess(elapsed, 1)
        self.assertIsInstance(errors[0], DagExecutionCancelled)
        self.assertEqual(result["runs_removed"], 1)
        with self.assertRaises(FileNotFoundError):
            self.run_store.load(run.id)

    def test_rerunning_one_node_invalidates_descendants_but_keeps_other_branches(self) -> None:
        workflow = self.save_workflow()
        run = self.executor.create_run(workflow, self.runtime_request())
        self.executor.execute_next_batch(run.id)
        before_rerun = self.executor.execute_next_batch(run.id)
        self.assertEqual(before_rerun.nodes["document_embed"].status, "succeeded")
        self.assertEqual(before_rerun.nodes["decompose"].status, "succeeded")

        rerun = self.executor.execute_node(run.id, "query")

        self.assertEqual(rerun.nodes["query"].status, "succeeded")
        self.assertEqual(rerun.nodes["documents"].status, "succeeded")
        self.assertEqual(rerun.nodes["document_embed"].status, "succeeded")
        self.assertEqual(rerun.nodes["decompose"].status, "pending")
        self.assertIsNone(rerun.nodes["decompose"].output)
        self.assertEqual(rerun.nodes["reader"].status, "pending")

    def test_run_resumes_with_persisted_outputs_after_executor_restart(self) -> None:
        workflow = self.save_workflow()
        run = self.executor.create_run(workflow, self.runtime_request())
        self.executor.execute_next_batch(run.id)
        self.executor.execute_next_batch(run.id)
        upstream_output = self.run_store.load(run.id).nodes["decompose"].output

        restarted_executor = WorkflowExecutor(
            self.registry,
            RunStore(Path(self.temporary_directory.name) / "runs"),
            ResultCache(Path(self.temporary_directory.name) / "cache"),
        )
        completed = restarted_executor.execute_all(run.id)

        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.nodes["decompose"].output, upstream_output)
        self.assertEqual(completed.nodes["reader"].status, "succeeded")
        self.assertIn("answer_json", completed.nodes["reader"].output)

    def test_same_inputs_reuse_cached_module_outputs(self) -> None:
        graph = WorkflowGraph(
            nodes=[
                WorkflowNode(
                    id="transform",
                    module_type="json_transformer",
                    position=CanvasPosition(x=0, y=0),
                    config={"mappings": {"source": "target"}},
                ),
                WorkflowNode(
                    id="inspect",
                    module_type="json_inspector",
                    position=CanvasPosition(x=200, y=0),
                ),
            ],
            edges=[WorkflowEdge(id="inspect", source="transform", target="inspect")],
        )
        workflow = self.workflow_store.save(
            "cache-flow",
            WorkflowSaveRequest(name="Cache Flow", graph=graph),
        )
        request = WorkflowExecutionRequest(
            inputs={"transform": {"any_json": {"source": 7}}}
        )
        first = self.executor.create_run(workflow, request)
        self.executor.execute_all(first.id)
        second = self.executor.create_run(workflow, request)
        completed = self.executor.execute_all(second.id)

        self.assertTrue(completed.nodes["transform"].cache_hit)
        self.assertFalse(completed.nodes["inspect"].cache_hit)

    def test_generated_and_cached_branches_feed_the_same_input_alternatively(self) -> None:
        graph = WorkflowGraph(
            nodes=[
                WorkflowNode(
                    id="query",
                    module_type="query_input",
                    position=CanvasPosition(x=0, y=0),
                ),
                WorkflowNode(
                    id="generated-inspector",
                    module_type="json_inspector",
                    position=CanvasPosition(x=200, y=-80),
                ),
                WorkflowNode(
                    id="cached-inspector",
                    module_type="json_inspector",
                    position=CanvasPosition(x=200, y=0),
                ),
            ],
            edges=[
                WorkflowEdge(
                    id="generated",
                    source="query",
                    target="generated-inspector",
                    source_branch="generated",
                    target_input="input",
                ),
                WorkflowEdge(
                    id="cached",
                    source="query",
                    target="cached-inspector",
                    source_branch="cached",
                    target_input="input",
                ),
            ],
        )
        workflow = self.workflow_store.save(
            "branch-flow",
            WorkflowSaveRequest(name="Branch Flow", graph=graph),
        )
        request = WorkflowExecutionRequest(
            inputs={"query": {"query": "질문 Q001"}}
        )

        first = self.executor.create_run(workflow, request)
        first = self.executor.execute_all(first.id)
        self.repository.save_cached_answer("Q001", "질문 Q001", "LLM 답변 Q001")
        second = self.executor.create_run(workflow, request)
        second = self.executor.execute_all(second.id)

        self.assertEqual(first.nodes["query"].outcome, "generated")
        self.assertEqual(second.nodes["query"].outcome, "cached")
        self.assertEqual(first.nodes["generated-inspector"].status, "succeeded")
        self.assertEqual(first.nodes["cached-inspector"].status, "skipped")
        self.assertEqual(second.nodes["generated-inspector"].status, "skipped")
        self.assertEqual(second.nodes["cached-inspector"].status, "succeeded")
        self.assertEqual(
            second.nodes["cached-inspector"].output,
            {
                "query_context": {
                    "question_id": "Q001",
                    "question_text": "질문 Q001",
                },
                "answer": "LLM 답변 Q001",
            },
        )

    def test_failed_output_branch_is_not_part_of_the_edge_contract(self) -> None:
        with self.assertRaises(ValidationError):
            WorkflowEdge.model_validate(
                {
                    "id": "failure",
                    "source": "query",
                    "target": "error-inspector",
                    "source_branch": "failed",
                }
            )

    def test_cycle_is_rejected_before_a_run_is_created(self) -> None:
        graph = self.graph()
        graph.edges.append(
            WorkflowEdge(id="cycle", source="reader", target="decompose")
        )
        workflow = self.workflow_store.save(
            "cycle-flow",
            WorkflowSaveRequest(name="Cycle", graph=graph),
        )

        with self.assertRaises(DagExecutionError):
            self.executor.create_run(workflow, self.runtime_request())

    def test_invalid_named_port_is_rejected(self) -> None:
        graph = self.graph()
        graph.edges[0].source_output = "missing_output"
        workflow = self.workflow_store.save(
            "bad-port",
            WorkflowSaveRequest(name="Bad port", graph=graph),
        )

        with self.assertRaises(DagExecutionError):
            self.executor.create_run(workflow, self.runtime_request())

    def test_workflow_run_api_executes_one_persisted_batch_at_a_time(self) -> None:
        root = Path(self.temporary_directory.name)
        application = FastAPI()
        application.include_router(
            create_api_router(
                self.repository,
                workflow_dir=root / "api-workflows",
                run_dir=root / "api-runs",
                cache_dir=root / "api-cache",
                embedding_artifact_dir=root / "api-embeddings",
                vector_index_dir=root / "api-vector-indexes",
                completion_client=StubCompletionClient(),
                embedding_encoder=StubEmbeddingEncoder(),
            )
        )
        client = TestClient(application)
        save_response = client.put(
            "/api/workflows/api-flow",
            json={"name": "API Flow", "graph": self.graph().model_dump()},
        )
        self.assertEqual(save_response.status_code, 200)

        create_response = client.post(
            "/api/workflows/api-flow/runs",
            json=self.runtime_request().model_dump(),
        )
        self.assertEqual(create_response.status_code, 200)
        run_id = create_response.json()["id"]

        cancel_response = client.post(f"/api/runs/{run_id}/cancel")
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], "queued")

        next_response = client.post(f"/api/runs/{run_id}/execute-next")
        self.assertEqual(next_response.status_code, 200)
        self.assertEqual(next_response.json()["nodes"]["query"]["status"], "succeeded")
        persisted_response = client.get(f"/api/runs/{run_id}")
        self.assertEqual(
            persisted_response.json()["nodes"]["query"]["output"],
            next_response.json()["nodes"]["query"]["output"],
        )
        single_node_response = client.post(
            f"/api/runs/{run_id}/nodes/decompose/execute"
        )
        self.assertEqual(single_node_response.status_code, 200)
        self.assertEqual(
            single_node_response.json()["nodes"]["decompose"]["status"],
            "succeeded",
        )
        self.assertEqual(
            single_node_response.json()["nodes"]["document_embed"]["status"],
            "pending",
        )
        second_batch_response = client.post(f"/api/runs/{run_id}/execute-next")
        self.assertEqual(second_batch_response.status_code, 200)
        third_batch_response = client.post(f"/api/runs/{run_id}/execute-next")
        self.assertEqual(third_batch_response.status_code, 200)
        self.repository.save_cached_answer("Q001", "질문 Q001", "LLM 답변 Q001")

        clear_response = client.delete("/api/cache")
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["runs_removed"], 1)
        self.assertGreaterEqual(
            clear_response.json()["cache_entries_removed"], 1
        )
        self.assertGreaterEqual(clear_response.json()["answers_removed"], 1)
        self.assertGreaterEqual(
            clear_response.json()["embedding_artifacts_removed"], 1
        )
        self.assertGreaterEqual(clear_response.json()["vector_indexes_removed"], 1)
        self.assertEqual(client.get(f"/api/runs/{run_id}").status_code, 404)
        self.assertEqual(client.get("/api/workflows/api-flow").status_code, 200)


class OpenAIEmbeddingEncoderTest(unittest.TestCase):
    def test_get_embedding_encoder_factory(self):
        from backend.bge_encoder import BgeEncoder
        from backend.embedding_factory import get_embedding_encoder
        from backend.openai_embedding_encoder import OpenAIEmbeddingEncoder

        openai_encoder = get_embedding_encoder("text-embedding-3-small")
        self.assertIsInstance(openai_encoder, OpenAIEmbeddingEncoder)

        bge_encoder = get_embedding_encoder("BAAI/bge-large-en-v1.5")
        self.assertIsInstance(bge_encoder, BgeEncoder)

    @patch("backend.openai_embedding_encoder.urlopen")
    def test_openai_embedding_encode_success(self, mock_urlopen):
        from backend.openai_embedding_encoder import OpenAIEmbeddingEncoder
        import io

        mock_response_data = json.dumps({
            "data": [
                {"index": 0, "embedding": [3.0, 4.0]},
                {"index": 1, "embedding": [1.0, 0.0]}
            ]
        }).encode("utf-8")

        class MockHTTPResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return mock_response_data

        mock_urlopen.return_value = MockHTTPResponse()

        encoder = OpenAIEmbeddingEncoder(
            model_name="text-embedding-3-small",
            api_key="test-key",
        )
        vectors = encoder.encode(["query 1", "query 2"])

        self.assertEqual(len(vectors), 2)
        # Check L2 normalization: [3, 4] normalized to [0.6, 0.8]
        self.assertAlmostEqual(vectors[0][0], 0.6)
        self.assertAlmostEqual(vectors[0][1], 0.8)
        self.assertAlmostEqual(vectors[1][0], 1.0)
        self.assertAlmostEqual(vectors[1][1], 0.0)


class PrebuiltIndexLoaderModuleTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.vector_index_dir = Path(self.temp_dir.name) / "vector_db"
        self.processed_dir = Path(self.temp_dir.name) / "processed"
        self.vector_index_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.vector_index_store = VectorIndexStore(self.vector_index_dir)
        self.prebuilt_json_path = self.processed_dir / "test_prebuilt.json"

        # Write sample prebuilt single JSON index file
        sample_payload = {
            "file_name": "Test_Workbook.xlsx",
            "workbook_hash": "a1b2c3d4e5f67890",
            "model": "BAAI/bge-large-en-v1.5",
            "dimension": 2,
            "items": [
                {
                    "sheet_name": "Key Stats",
                    "cell_address": "E10",
                    "text": "Sheet: Key Stats | Row Header: Total Revenue | Column Header: 2025-12-31 | Cell Value: 1000",
                    "embedding": [1.0, 0.0],
                },
                {
                    "sheet_name": "Key Stats",
                    "cell_address": "E11",
                    "text": "Sheet: Key Stats | Row Header: Net Income | Column Header: 2025-12-31 | Cell Value: 200",
                    "embedding": [0.0, 1.0],
                },
            ],
        }
        self.prebuilt_json_path.write_text(json.dumps(sample_payload), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prebuilt_parquet_loader_execution(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        from backend.modules.prebuilt_index_loader import (
            PrebuiltIndexLoaderInputDTO,
            PrebuiltIndexLoaderModule,
        )

        parquet_path = self.processed_dir / "test_prebuilt.parquet"
        table = pa.table(
            {
                "cell_id": ["Key Stats Cell E10", "Key Stats Cell E11"],
                "sheet_name": ["Key Stats", "Key Stats"],
                "cell_coord": ["E10", "E11"],
                "row_header": [["Total Revenue"], ["Net Income"]],
                "column_header": [["2025-12-31"], ["2025-12-31"]],
                "cell_value": ["1000", "200"],
                "variant": ["header_with_value", "header_with_value"],
                "text": [
                    "Sheet: Key Stats | Row Header: Total Revenue | Column Header: 2025-12-31 | Cell Value: 1000",
                    "Sheet: Key Stats | Row Header: Net Income | Column Header: 2025-12-31 | Cell Value: 200",
                ],
                "embedding": pa.array(
                    [[1.0, 0.0], [0.0, 1.0]],
                    type=pa.list_(pa.float32()),
                ),
            }
        ).replace_schema_metadata(
            {
                b"file_name": b"Test_Workbook.xlsx",
                b"workbook_hash": b"a1b2c3d4e5f67890",
                b"model": b"BAAI/bge-large-en-v1.5",
            }
        )
        pq.write_table(table, parquet_path)

        loader = PrebuiltIndexLoaderModule(
            vector_index_store=self.vector_index_store,
            search_dirs=[self.processed_dir],
        )
        result = loader.execute(
            PrebuiltIndexLoaderInputDTO(file_name=parquet_path.name)
        )

        self.assertEqual(
            result["document_output"]["file_name"],
            "Test_Workbook.xlsx",
        )
        self.assertEqual(result["index_output"]["document_count"], 2)
        self.assertEqual(result["index_output"]["dimension"], 2)
        self.assertEqual(
            result["index_output"]["model"],
            "BAAI/bge-large-en-v1.5",
        )

    def test_prebuilt_index_loader_execution(self):
        from backend.modules.prebuilt_index_loader import (
            PrebuiltIndexLoaderInputDTO,
            PrebuiltIndexLoaderModule,
        )

        loader = PrebuiltIndexLoaderModule(
            vector_index_store=self.vector_index_store,
            search_dirs=[self.processed_dir],
        )

        result = loader.execute(
            PrebuiltIndexLoaderInputDTO(file_name="test_prebuilt.json")
        )

        self.assertIn("document_output", result)
        self.assertIn("index_output", result)

        doc_out = result["document_output"]
        idx_out = result["index_output"]

        self.assertEqual(doc_out["file_name"], "Test_Workbook.xlsx")
        self.assertEqual(len(doc_out["items"]), 2)
        self.assertEqual(idx_out["document_count"], 2)
        self.assertEqual(idx_out["dimension"], 2)
        self.assertEqual(len(idx_out["index_id"]), 64)

        from backend.modules.bm25_retriever import (
            Bm25RetrieverExecutionDTO,
            Bm25RetrieverModule,
        )
        from backend.modules.dense_retriever import (
            DenseRetrieverExecutionDTO,
            DenseRetrieverModule,
        )

        bm25_retriever = Bm25RetrieverModule()
        dense_retriever = DenseRetrieverModule(index_store=self.vector_index_store)

        index_input = {
            "index_id": idx_out["index_id"],
            "file_name": idx_out["file_name"],
            "workbook_hash": idx_out["workbook_hash"],
            "model": idx_out["model"],
            "dimension": idx_out["dimension"],
            "document_count": idx_out["document_count"],
        }
        dense_res = dense_retriever.execute(
            DenseRetrieverExecutionDTO.model_validate({
                "query_input": {
                    "query_context": sample_query_context("q1", "Revenue"),
                    "items": {"Revenue": [1.0, 0.0]},
                },
                "index_input": index_input,
            })
        )
        self.assertTrue(len(dense_res["items"]) > 0)

        bm25_res = bm25_retriever.execute(
            Bm25RetrieverExecutionDTO.model_validate({
                "query_input": {
                    "query_context": sample_query_context("q1", "Revenue"),
                    "subqueries": ["Total Revenue"],
                },
                "document_input": doc_out,
            })
        )
        self.assertTrue(len(bm25_res["items"]) > 0)


if __name__ == "__main__":
    unittest.main()
