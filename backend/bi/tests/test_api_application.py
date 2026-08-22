from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from backend.bi.api_routes import BiApiServices, create_bi_app
from backend.bi.materialization_models import BiMaterializationOutcome
from backend.bi.models import BiMaterializationRequest, JobId
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.question_api_fakes import UnusedQuestionApi


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 20, tzinfo=UTC)


class UnusedRunner:
    def materialize(
        self,
        request: BiMaterializationRequest,
        job_id: JobId,
    ) -> BiMaterializationOutcome:
        raise AssertionError("application contract test must not run materialization")


class BiApiApplicationTests(unittest.TestCase):
    def test_openapi_declares_bi_tag_and_typed_conflict_response(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            services = BiApiServices(
                FileBiSnapshotStore(Path(directory)),
                UnusedRunner(),
                FixedClock(),
                UnusedQuestionApi(),
            )

            # When
            schema = create_bi_app(services).openapi()

            # Then
            self.assertEqual(schema["tags"][0]["name"], "BI")
            conflict = schema["paths"]["/api/bi/materializations"]["post"][
                "responses"
            ]["409"]
            self.assertEqual(
                conflict["content"]["application/json"]["schema"]["$ref"],
                "#/components/schemas/BiApiFailure",
            )

    def test_store_corruption_returns_generic_typed_failure(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "companies.json").write_text("not-json", encoding="utf-8")
            services = BiApiServices(
                FileBiSnapshotStore(root),
                UnusedRunner(),
                FixedClock(),
                UnusedQuestionApi(),
            )

            # When
            with TestClient(
                create_bi_app(services),
                raise_server_exceptions=False,
            ) as client:
                response = client.get("/api/bi/companies")

            # Then
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {"detail": "BI artifact is corrupted"})
            self.assertNotIn(str(root), response.text)


if __name__ == "__main__":
    unittest.main()
