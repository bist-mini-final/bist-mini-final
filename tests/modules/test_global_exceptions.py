from __future__ import annotations

import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.main import register_global_exception_handlers
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

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_pipeline_error_handling(self) -> None:
        res = self.client.get("/test/error/pipeline")
        self.assertEqual(res.status_code, 500)
        data = res.json()
        self.assertEqual(data["error_code"], "PIPELINE_ERROR")
        self.assertEqual(data["module_type"], "test_mod")

    def test_validation_error_handling(self) -> None:
        res = self.client.get("/test/error/validation")
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertEqual(data["error_code"], "MODULE_VALIDATION_ERROR")
        self.assertEqual(data["module_type"], "reader")

    def test_provider_api_error_handling(self) -> None:
        res = self.client.get("/test/error/provider")
        self.assertEqual(res.status_code, 502)
        data = res.json()
        self.assertEqual(data["error_code"], "PROVIDER_API_ERROR")
        self.assertEqual(data["module_type"], "decomposer")
        self.assertEqual(data["details"]["provider"], "openai")

    def test_storage_error_handling(self) -> None:
        res = self.client.get("/test/error/storage")
        self.assertEqual(res.status_code, 500)
        data = res.json()
        self.assertEqual(data["error_code"], "STORAGE_ERROR")
        self.assertEqual(data["module_type"], "pgvector")

    def test_parsing_error_handling(self) -> None:
        res = self.client.get("/test/error/parsing")
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertEqual(data["error_code"], "DOCUMENT_PARSING_ERROR")
        self.assertEqual(data["module_type"], "luna_vlm")

    def test_unhandled_exception_handling(self) -> None:
        res = self.client.get("/test/error/unhandled")
        self.assertEqual(res.status_code, 500)
        data = res.json()
        self.assertEqual(data["error_code"], "INTERNAL_SERVER_ERROR")
