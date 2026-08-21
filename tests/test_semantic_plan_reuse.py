import json
import unittest

from modules.query.adaptive_query_decomposer import AdaptiveQueryDecomposerModule
from backend.semantic_matching.plan_validation import validate_plan_reuse


def structured(row: str, period: str) -> str:
    return f"Sheet: Key_Stats | Row Header: {row} | Column Header: {period} | Cell Value: ?"


class RecordingCompletionClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, _model, _messages):
        self.calls += 1
        return json.dumps([structured("Total Revenue", "FY2023")])


class SemanticPlanValidationTests(unittest.TestCase):
    def test_rejects_explicit_year_mismatch(self) -> None:
        result = validate_plan_reuse(
            "IBM의 2023년 매출은?",
            "get_ibm_key_financials",
            [structured("Total Revenue", "FY2025")],
        )
        self.assertFalse(result.reusable)
        self.assertIn("periods", result.reason)

    def test_rejects_incomplete_recent_year_trend(self) -> None:
        result = validate_plan_reuse(
            "IBM 장기부채 최근 3개년 흐름을 알려줘",
            "get_ibm_key_financials",
            [structured("Long-Term Debt", "FY2023")],
        )
        self.assertFalse(result.reusable)

    def test_rejects_target_entity_mismatch(self) -> None:
        result = validate_plan_reuse(
            "IBM 2025년 매출은?",
            "get_bac_company_profile",
            [structured("Total Revenue", "FY2025")],
        )
        self.assertFalse(result.reusable)

    def test_rejects_missing_requested_metric(self) -> None:
        result = validate_plan_reuse(
            "IBM 2025년 EBITDA는?",
            "get_ibm_key_financials",
            [structured("Total Revenue", "FY2025")],
        )
        self.assertFalse(result.reusable)

    def test_accepts_matching_multi_period_plan(self) -> None:
        result = validate_plan_reuse(
            "IBM의 2024년부터 2025년까지 매출 추이",
            "get_ibm_key_financials",
            [
                structured("Total Revenue", "FY2024"),
                structured("Total Revenue", "FY2025"),
            ],
        )
        self.assertTrue(result.reusable, result.reason)

    def test_cash_flow_metric_is_not_mistaken_for_trend_request(self) -> None:
        result = validate_plan_reuse(
            "IBM의 2025년 영업현금흐름은?",
            "get_ibm_key_financials",
            [structured("Cash from Ops.", "FY2025")],
        )
        self.assertTrue(result.reusable, result.reason)

    def test_rejects_ltm_question_reusing_old_fiscal_year(self) -> None:
        result = validate_plan_reuse(
            "IBM의 최근 12개월 EBITDA는?",
            "get_ibm_key_financials",
            [structured("EBITDA", "FY2023")],
        )
        self.assertFalse(result.reusable)
        self.assertIn("periods", result.reason)

    def test_adaptive_decomposer_falls_back_on_unsafe_plan(self) -> None:
        client = RecordingCompletionClient()
        result = AdaptiveQueryDecomposerModule(client).run({
            "query_context": {
                "question_id": "q",
                "question_text": "IBM의 2023년 매출은?",
            },
            "semantic_match": {
                "matched": True,
                "target": "get_ibm_key_financials",
                "confidence": 0.95,
                "sheets": ["Key_Stats"],
                "reason": "nearby example",
                "matches": [],
                "subqueries": [structured("Total Revenue", "FY2025")],
            },
        })
        self.assertEqual(client.calls, 1)
        self.assertTrue(any("FY2023" in item for item in result["subqueries"]))

    def test_adaptive_decomposer_falls_back_below_plan_threshold(self) -> None:
        client = RecordingCompletionClient()
        AdaptiveQueryDecomposerModule(client).run({
            "query_context": {
                "question_id": "q",
                "question_text": "IBM의 2023년 매출은?",
            },
            "semantic_match": {
                "matched": True,
                "target": "get_ibm_key_financials",
                "confidence": 0.79,
                "sheets": ["Key_Stats"],
                "reason": "below plan threshold",
                "matches": [],
                "subqueries": [structured("Total Revenue", "FY2023")],
            },
        })
        self.assertEqual(client.calls, 1)

    def test_adaptive_decomposer_falls_back_when_plan_is_missing(self) -> None:
        client = RecordingCompletionClient()
        AdaptiveQueryDecomposerModule(client).run({
            "query_context": {
                "question_id": "q",
                "question_text": "IBM의 2023년 매출은?",
            },
            "semantic_match": {
                "matched": True,
                "target": "get_ibm_key_financials",
                "confidence": 0.95,
                "sheets": ["Key_Stats"],
                "reason": "route only",
                "matches": [],
            },
        })
        self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
