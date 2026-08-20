import json
import unittest
from collections import Counter
from pathlib import Path

from backend.api.benchmark_routes import BenchmarkCase
from backend.semantic_matching.catalog import load_examples


ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = ROOT / "data" / "benchmark_sets" / "semantic-safety-holdout-30.json"
CORE = ROOT / "data" / "benchmark_sets" / "semantic-decomposition-core-6.json"


class SemanticSafetyHoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = json.loads(HOLDOUT.read_text(encoding="utf-8"))
        cls.cases = [BenchmarkCase.model_validate(item) for item in raw]

    def test_has_thirty_unique_cases(self) -> None:
        self.assertEqual(len(self.cases), 30)
        self.assertEqual(len({case.id for case in self.cases}), 30)
        self.assertEqual(len({case.question.casefold() for case in self.cases}), 30)

    def test_has_no_exact_catalog_question_overlap(self) -> None:
        catalog_questions = {item.question.strip().casefold() for item in load_examples()}
        overlap = [
            case.id
            for case in self.cases
            if case.question.strip().casefold() in catalog_questions
        ]
        self.assertEqual(overlap, [])

    def test_covers_all_targets_and_negative_abstentions(self) -> None:
        target_counts = Counter(
            case.expected_target for case in self.cases if case.expected_target
        )
        self.assertEqual(
            set(target_counts),
            {
                "get_ibm_key_financials",
                "get_ibm_capitalization",
                "get_ibm_financial_ratios",
                "get_bac_ownership_list",
                "get_bac_company_profile",
                "get_virtual_company_financials",
                "get_virtual_company_headcount",
            },
        )
        self.assertEqual(sum(case.expected_abstain for case in self.cases), 6)
        self.assertEqual(sum(case.expected_plan is not None for case in self.cases), 12)

    def test_fast_core_set_can_be_scored_before_retrieval(self) -> None:
        cases = [
            BenchmarkCase.model_validate(item)
            for item in json.loads(CORE.read_text(encoding="utf-8"))
        ]
        self.assertEqual(len(cases), 6)
        self.assertTrue(all(case.expected_sheets for case in cases))
        self.assertTrue(all(case.expected_plan is not None for case in cases))


if __name__ == "__main__":
    unittest.main()
