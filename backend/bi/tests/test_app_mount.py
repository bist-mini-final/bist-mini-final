from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.bi.composition import create_bi_services
from backend.storage.db_manager import DatabaseManager

with patch.object(DatabaseManager, "ensure_schema"):
    from app import create_app


def create_test_app() -> FastAPI:
    with patch.object(DatabaseManager, "ensure_schema"):
        return create_app()


class ProductionBiMountTests(TestCase):
    def test_production_app_connects_indexing_completion_to_bi(self) -> None:
        with patch(
            "backend.api.router.create_bi_workflow_dispatcher",
            create=True,
        ) as dispatcher_factory:
            create_test_app()

        dispatcher_factory.assert_called_once()

    def test_production_app_mounts_bi_query_routes(self) -> None:
        with TemporaryDirectory() as directory:
            isolated_services = partial(
                create_bi_services,
                artifact_dir=Path(directory),
            )
            with patch(
                "backend.api.router.create_bi_services",
                isolated_services,
            ):
                with TestClient(create_test_app()) as client:
                    response = client.get("/api/bi/companies")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"companies": []})

    def test_production_openapi_exposes_bi_contract(self) -> None:
        schema = create_test_app().openapi()

        company_operation = schema["paths"]["/api/bi/companies"]["get"]
        self.assertEqual(company_operation["tags"], ["BI"])
