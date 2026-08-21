import json
import unittest

from backend.modules.template_query_decomposer import (
    TemplateQueryDecomposerModule,
    build_template_subqueries,
)


class RecordingCompletionClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, _model, _messages):
        self.calls += 1
        return json.dumps([
            "Sheet: Key_Stats | Row Header: CEO | Column Header: FY2025 | Cell Value: ?"
        ])


def semantic_match() -> dict:
    return {
        "matched": False,
        "target": None,
        "confidence": 0.0,
        "sheets": [],
        "reason": "test",
        "matches": [],
    }


class TemplateQueryDecomposerTests(unittest.TestCase):
    def test_fills_metric_and_year_without_llm(self) -> None:
        client = RecordingCompletionClient()
        result = TemplateQueryDecomposerModule(client).run({
            "query_context": {"question_id": "q", "question_text": "IBM의 2023년 총매출은?"},
            "semantic_match": semantic_match(),
        })
        self.assertEqual(client.calls, 0)
        self.assertTrue(any("Income_Statement" in item and "Total Revenue" in item and "FY2023" in item for item in result["subqueries"]))

    def test_expands_calculation_into_source_cells(self) -> None:
        result, reason = build_template_subqueries("IBM 2025년 FCF를 영업현금흐름과 CapEx로 계산해줘")
        self.assertIsNotNone(result, reason)
        self.assertTrue(any("Cash from Ops." in item for item in result or []))
        self.assertTrue(any("Capital Expenditure" in item for item in result or []))

    def test_falls_back_for_company_profile_intent(self) -> None:
        client = RecordingCompletionClient()
        TemplateQueryDecomposerModule(client).run({
            "query_context": {"question_id": "q", "question_text": "Bank of America CEO는 누구야?"},
            "semantic_match": semantic_match(),
        })
        self.assertEqual(client.calls, 1)

    def test_requires_an_explicit_period(self) -> None:
        result, reason = build_template_subqueries("IBM의 매출은?")
        self.assertIsNone(result)
        self.assertIn("period", reason)


if __name__ == "__main__":
    unittest.main()
