"""Unit tests for OpenAPI x-tagGroups generation, external module schemas injection, and module route endpoints."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.entrypoints.asgi import create_app


class OpenApiAndModuleRoutesTests(unittest.TestCase):
    """Tests for OpenAPI schema generation, ReDoc hierarchical groups, and module API endpoints."""

    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_openapi_contains_hierarchical_xtag_groups(self) -> None:
        """Verify that openapi.json contains x-tagGroups matching ReDoc specifications."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("x-tagGroups", data)
        tag_groups = data["x-tagGroups"]
        group_names = [group["name"] for group in tag_groups]

        self.assertIn("1. 시스템 및 인프라", group_names)
        self.assertIn("2. RAG 파이프라인 모듈", group_names)
        self.assertIn("3. DAG 워크플로 엔진", group_names)
        self.assertIn("4. BI 대시보드 및 분석 엔진", group_names)
        self.assertIn("5. 기업 비교 분석", group_names)
        self.assertIn("6. RAG 벤치마크 평가", group_names)

    def test_openapi_schemas_contain_external_module_dtos(self) -> None:
        """Verify that components.schemas contains Pydantic DTOs from modules/."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schemas = response.json().get("components", {}).get("schemas", {})

        # Key DTOs from modules/*
        expected_dtos = [
            "DecomposerInputDTO",
            "DecomposerConfigDTO",
            "RetrievalPlanDTO",
            "QueryInputDTO",
            "QueryContextDTO",
            "CellTextEmbedderInputDTO",
            "PgVectorRetrieverInputDTO",
            "RankedSearchResultDTO",
            "ReaderInputDTO",
            "ReaderOutputDTO",
            "CellEvidenceDTO",
            "ChatMessageResponse",
        ]
        for dto_name in expected_dtos:
            self.assertIn(
                dto_name,
                schemas,
                f"Expected {dto_name} to be injected into OpenAPI components.schemas",
            )

    def test_openapi_exposes_only_the_versioned_api_namespace(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        product_paths = [path for path in paths if path.startswith("/api/")]

        self.assertTrue(product_paths)
        self.assertTrue(all(path.startswith("/api/v1/") for path in product_paths))
        self.assertIn("/api/v1/company-comparisons/snapshot", paths)
        self.assertIn("/api/v1/company-comparisons/snapshot/refresh", paths)
        self.assertIn("/api/v1/data-sources/files", paths)
        self.assertIn("/api/v1/data-sources/indexes", paths)
        self.assertIn("/api/v1/data-sources/ingestion-jobs", paths)
        self.assertNotIn("/api/v1/company-comparisons/analyze", paths)
        self.assertNotIn("/api/v1/company-comparisons/league", paths)

    def test_legacy_api_namespace_remains_a_hidden_compatibility_alias(self) -> None:
        canonical = self.client.get("/api/v1/modules/categories")
        legacy = self.client.get("/api/modules/categories")

        self.assertEqual(canonical.status_code, 200)
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(canonical.json(), legacy.json())
        self.assertEqual(legacy.headers["Deprecation"], "true")
        self.assertIn(
            "/api/v1/modules/categories",
            legacy.headers["Link"],
        )
        self.assertNotIn("Deprecation", canonical.headers)

    def test_chatbot_documentation_alias_matches_the_canonical_chat_api(self) -> None:
        canonical = self.client.get(
            "/api/v1/chat/sessions", params={"client_id": "test-client-0001"}
        )
        alias = self.client.get(
            "/api/v1/chatbot/sessions", params={"client_id": "test-client-0001"}
        )
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertEqual(canonical.status_code, alias.status_code)
        self.assertEqual(canonical.json(), alias.json())
        self.assertTrue(any(path.startswith("/api/v1/chat/") for path in paths))
        self.assertFalse(any(path.startswith("/api/v1/chatbot/") for path in paths))

    def test_module_categories_endpoint(self) -> None:
        """Verify GET /api/v1/modules/categories returns grouped module contracts."""
        response = self.client.get("/api/v1/modules/categories")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("categories", payload)
        categories = payload["categories"]
        self.assertGreater(len(categories), 0)

        all_types: list[str] = []
        for cat in categories:
            self.assertIn("category", cat)
            self.assertIn("count", cat)
            self.assertIn("module_types", cat)
            self.assertIn("modules", cat)
            all_types.extend(cat["module_types"])

        self.assertIn("decomposer", all_types)
        self.assertIn("reader", all_types)
        self.assertIn("pgvector_retriever", all_types)

    def test_module_schemas_endpoint(self) -> None:
        """Verify GET /api/v1/modules/schemas returns all input/config/output JSON schemas."""
        response = self.client.get("/api/v1/modules/schemas")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("schemas", payload)
        schemas = payload["schemas"]

        self.assertIn("decomposer", schemas)
        decomposer_schema = schemas["decomposer"]
        self.assertIn("input_schema", decomposer_schema)
        self.assertIn("config_schema", decomposer_schema)
        self.assertIn("output_schema", decomposer_schema)

    def test_get_single_module_detail(self) -> None:
        """Verify GET /api/v1/modules/{module_type} returns one contract and docs."""
        response = self.client.get("/api/v1/modules/decomposer")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "decomposer")
        self.assertIn("input_schema", payload)
        self.assertIn("output_schema", payload)

        # Markdown docs endpoint
        doc_resp = self.client.get("/api/v1/modules/decomposer/docs")
        self.assertEqual(doc_resp.status_code, 200)
        self.assertIn("decomposer", doc_resp.text.lower())

    def test_get_nonexistent_module_returns_404(self) -> None:
        """Verify 404 for invalid module type."""
        response = self.client.get("/api/v1/modules/non_existent_module_type_123")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
