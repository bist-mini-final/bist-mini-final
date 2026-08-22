import unittest
from unittest.mock import patch

from backend.bi.models import BiMaterializationSource
from backend.bi.profile_models import BiProfileRetrievalRequest
from backend.bi.profile_sheet_catalog import PostgresBiProfileEvidenceRetriever


class FakeCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def execute(self, query, params=None) -> None:
        del params
        self.queries.append(query)

    def fetchall(self):
        return [
            {
                "cell_id": "sheet:B2",
                "sheet_name": "Key Statistics",
                "cell_coord": "B2",
                "source_text": "TTM 2Q26",
            }
        ]


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def cursor(self, cursor_factory=None):
        del cursor_factory
        return self._cursor


class ProfileSheetCatalogTests(unittest.TestCase):
    def test_period_discovery_exposes_non_fy_ltm_headers_to_the_llm(self) -> None:
        cursor = FakeCursor()
        request = BiProfileRetrievalRequest(
            request_id="profile-test",
            source=BiMaterializationSource(
                file_name="company.xlsx",
                workbook_hash="a" * 64,
                index_id="index-1",
            ),
            sheet_name="Key Statistics",
            question="사용 가능한 기간을 모두 찾아라.",
        )

        with patch(
            "backend.bi.profile_sheet_catalog.get_pooled_raw_connection",
            return_value=FakeConnection(cursor),
        ):
            context = PostgresBiProfileEvidenceRetriever().retrieve(request)

        candidate_query = next(
            query for query in cursor.queries if "WITH candidates" in query
        )
        self.assertNotIn("~* '(LTM|FY", candidate_query)
        self.assertEqual(context.cells[0].source_text, "TTM 2Q26")


if __name__ == "__main__":
    unittest.main()
