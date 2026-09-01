from __future__ import annotations

import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.entrypoints.asgi import register_global_exception_handlers
from backend.shared.domain import ResourceNotFoundError
from modules.common.exceptions import (
    DocumentParsingError,
    ModuleValidationError,
    PipelineBaseError,
    ProviderApiError,
    StorageError,
)


class GlobalExceptionHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        register_global_exception_handlers(self.app)

        @self.app.get("/test/error/pipeline")
        def raise_pipeline():
            raise PipelineBaseError("기본 파이프라인 오류", module_type="test_mod")

        @self.app.get("/test/error/validation")
        def raise_validation():
            raise ModuleValidationError("입력 검증 실패", module_type="reader")

        @self.app.get("/test/error/provider")
        def raise_provider():
            raise ProviderApiError("OpenAI Rate Limit", module_type="decomposer", provider="openai")

        @self.app.get("/test/error/storage")
        def raise_storage():
            raise StorageError("Postgres connection timeout", module_type="pgvector")

        @self.app.get("/test/error/parsing")
        def raise_parsing():
            raise DocumentParsingError("Excel sheet corrupted", module_type="luna_vlm")

        @self.app.get("/test/error/unhandled")
        def raise_unhandled():
            raise RuntimeError("Unexpected internal crash")

        @self.app.get("/test/error/http")
        def raise_http():
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "retryable": True,
                },
            )

        @self.app.get("/test/error/application")
        def raise_application():
            error = ResourceNotFoundError("대상을 찾을 수 없습니다")
            error.code = "TEST_RESOURCE_NOT_FOUND"
            raise error

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_pipeline_error_handling(self) -> None:
        res = self.client.get("/test/error/pipeline")
        self.assertEqual(res.status_code, 500)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "PIPELINE_ERROR")
        self.assertEqual(detail["context"]["module_type"], "test_mod")

    def test_validation_error_handling(self) -> None:
        res = self.client.get("/test/error/validation")
        self.assertEqual(res.status_code, 422)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "MODULE_VALIDATION_ERROR")
        self.assertEqual(detail["context"]["module_type"], "reader")

    def test_provider_api_error_handling(self) -> None:
        res = self.client.get("/test/error/provider")
        self.assertEqual(res.status_code, 502)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "PROVIDER_API_ERROR")
        self.assertEqual(detail["context"]["module_type"], "decomposer")
        self.assertEqual(detail["context"]["provider"], "openai")

    def test_storage_error_handling(self) -> None:
        res = self.client.get("/test/error/storage")
        self.assertEqual(res.status_code, 500)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "STORAGE_ERROR")
        self.assertEqual(detail["context"]["module_type"], "pgvector")

    def test_parsing_error_handling(self) -> None:
        res = self.client.get("/test/error/parsing")
        self.assertEqual(res.status_code, 422)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "DOCUMENT_PARSING_ERROR")
        self.assertEqual(detail["context"]["module_type"], "luna_vlm")

    def test_unhandled_exception_handling(self) -> None:
        res = self.client.get("/test/error/unhandled")
        self.assertEqual(res.status_code, 500)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "INTERNAL_SERVER_ERROR")
        self.assertTrue(detail["retryable"])

    def test_http_exception_preserves_structured_detail(self) -> None:
        res = self.client.get("/test/error/http")
        self.assertEqual(res.status_code, 503)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "WORKFLOW_QUEUE_UNAVAILABLE")
        self.assertTrue(detail["retryable"])

    def test_application_error_uses_shared_error_contract(self) -> None:
        res = self.client.get("/test/error/application")
        self.assertEqual(res.status_code, 404)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "TEST_RESOURCE_NOT_FOUND")
        self.assertEqual(detail["message"], "대상을 찾을 수 없습니다")

    def test_healthz_and_probes(self) -> None:
        from backend.entrypoints.asgi import create_app

        prod_app = create_app()
        client = TestClient(prod_app)

        health = client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "healthy")
        self.assertIn("X-Process-Time", health.headers)
        self.assertIn("X-Request-ID", health.headers)
        self.assertEqual(health.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(health.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", health.headers["Content-Security-Policy"])

        live = client.get("/livez")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["status"], "alive")
