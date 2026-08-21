import unittest
import json
from pathlib import Path
from types import SimpleNamespace

from backend.api.benchmark_routes import (
    BenchmarkCase,
    ExpectedPlan,
    _intermediate_score,
    _plan_score,
    _route_score,
    _run_metrics,
    _sheet_score,
    _workflow_for_scope,
)
from backend.engine.workflows import WorkflowDocument


class BenchmarkSemanticMetricsTests(unittest.TestCase):
    def test_adaptive_usage_marks_llm_fallback_even_for_matched_route(self) -> None:
        adaptive = SimpleNamespace(
            elapsed_ms=10,
            usage={"total_tokens": 30},
            cost_usd=0.001,
            cache_hit=False,
            output={},
            module_type="adaptive_query_decomposer",
            input_payload={"semantic_match": {"matched": True}},
            node_id="adaptive",
            status="succeeded",
        )
        run = SimpleNamespace(id="run", status="completed", nodes={"adaptive": adaptive})
        metrics = _run_metrics(run)
        self.assertEqual(metrics["llm_fallback_calls"], 1)
        self.assertIs(metrics["plan_reused"], False)

    def test_adaptive_without_usage_marks_plan_reuse(self) -> None:
        adaptive = SimpleNamespace(
            elapsed_ms=10,
            usage=None,
            cost_usd=None,
            cache_hit=False,
            output={},
            module_type="adaptive_query_decomposer",
            input_payload={"semantic_match": {"matched": True}},
            node_id="adaptive",
            status="succeeded",
        )
        run = SimpleNamespace(id="run", status="completed", nodes={"adaptive": adaptive})
        metrics = _run_metrics(run)
        self.assertEqual(metrics["llm_fallback_calls"], 0)
        self.assertIs(metrics["plan_reused"], True)

    def test_default_decomposer_plan_is_available_for_fair_scoring(self) -> None:
        decomposer = SimpleNamespace(
            elapsed_ms=10,
            usage={"total_tokens": 30},
            cost_usd=0.001,
            cache_hit=False,
            output={
                "subqueries": [
                    "Sheet: Income_Statement | Row Header: Total Revenue | Column Header: FY2025 | Cell Value: ?"
                ]
            },
            module_type="decomposer",
            input_payload={},
            node_id="decomposer",
            status="succeeded",
        )
        run = SimpleNamespace(id="run", status="completed", nodes={"decomposer": decomposer})
        metrics = _run_metrics(run)
        self.assertEqual(metrics["decomposition"]["source"], "llm_decomposer")
        self.assertEqual(len(metrics["decomposition"]["subqueries"]), 1)

    def test_route_abstention_remains_separate_from_wrong_attempt(self) -> None:
        case = BenchmarkCase(
            id="q",
            question="question",
            expected_target="get_ibm_key_financials",
        )
        abstained = _route_score(case, {"matched": False, "target": None, "sheets": []})
        wrong = _route_score(case, {"matched": True, "target": "get_bac_company_profile", "sheets": []})
        self.assertFalse(abstained["correct"])
        self.assertFalse(wrong["correct"])
        self.assertFalse(abstained["target_correct"])

    def test_expected_abstention_scores_only_an_unmatched_route(self) -> None:
        case = BenchmarkCase(
            id="negative",
            question="오늘 서울 날씨는?",
            expected_abstain=True,
        )
        abstained = _route_score(case, {"matched": False, "target": None, "sheets": []})
        false_accept = _route_score(case, {"matched": True, "target": "get_ibm_key_financials", "sheets": []})
        self.assertTrue(abstained["correct"])
        self.assertFalse(false_accept["correct"])
        self.assertTrue(abstained["expected_abstain"])

    def test_plan_score_uses_canonical_metrics_and_periods(self) -> None:
        case = BenchmarkCase(
            id="plan",
            question="IBM 2024년과 2025년 매출",
            expected_plan=ExpectedPlan(metrics=["revenue"], periods=[2024, 2025]),
        )
        score = _plan_score(case, {
            "source": "semantic_reuse",
            "subqueries": [
                "Sheet: Income_Statement | Row Header: Total Revenue | Column Header: FY2024 | Cell Value: ?",
                "Sheet: Income_Statement | Row Header: Revenue | Column Header: FY2025 | Cell Value: ?",
            ],
        })
        self.assertTrue(score["correct"])
        self.assertEqual(score["actual_metrics"], ["revenue"])
        self.assertEqual(score["actual_periods"], [2024, 2025])

    def test_extra_routed_sheet_fails_exact_match_but_keeps_recall(self) -> None:
        case = BenchmarkCase(
            id="sheet",
            question="IBM 총자산",
            expected_target="get_ibm_key_financials",
            expected_sheets=["Balance_Sheet"],
        )
        score = _route_score(case, {
            "matched": True,
            "target": "get_ibm_key_financials",
            "sheets": ["Balance_Sheet", "Income_Statement"],
        })
        self.assertFalse(score["correct"])
        self.assertEqual(score["sheet_recall"], 1.0)
        self.assertEqual(score["sheet_precision"], 0.5)

    def test_sheet_score_uses_router_and_combines_strictly(self) -> None:
        case = BenchmarkCase(
            id="sheet-plan",
            question="IBM 2025년 매출",
            expected_sheets=["Income_Statement"],
            expected_plan=ExpectedPlan(metrics=["revenue"], periods=[2025]),
        )
        decomposition = {
            "source": "semantic_reuse",
            "subqueries": [
                "Sheet: Income_Statement | Row Header: Total Revenue | Column Header: FY2025 | Cell Value: ?"
            ],
        }
        router = {
            "matched": True,
            "target": "get_ibm_key_financials",
            "sheets": ["Income_Statement"],
        }
        sheet_score = _sheet_score(case, router, decomposition)
        plan_score = _plan_score(case, decomposition)
        combined = _intermediate_score(case, _route_score(case, router), plan_score, sheet_score)
        self.assertTrue(sheet_score["correct"])
        self.assertTrue(combined["correct"])

    def test_plan_score_rejects_unrequested_extra_metric(self) -> None:
        case = BenchmarkCase(
            id="extra",
            question="IBM 2025년 매출",
            expected_plan=ExpectedPlan(metrics=["revenue"], periods=[2025]),
        )
        score = _plan_score(case, {
            "source": "semantic_reuse",
            "subqueries": [
                "Sheet: Income_Statement | Row Header: Total Revenue | Column Header: FY2025 | Cell Value: ?",
                "Sheet: Income_Statement | Row Header: EBITDA | Column Header: FY2025 | Cell Value: ?",
            ],
        })
        self.assertFalse(score["correct"])
        self.assertEqual(score["metric_recall"], 1.0)
        self.assertEqual(score["metric_precision"], 0.5)

    def test_unspecified_sheet_is_not_a_baseline_routing_error(self) -> None:
        case = BenchmarkCase(
            id="baseline",
            question="IBM 2025년 매출",
            expected_sheets=["Income_Statement"],
            expected_plan=ExpectedPlan(metrics=["revenue"], periods=[2025]),
        )
        decomposition = {
            "source": "llm_decomposer",
            "subqueries": [
                "Sheet: ? | Row Header: Total Revenue | Column Header: FY2025 | Cell Value: ?"
            ],
        }
        sheet_score = _sheet_score(case, None, decomposition)
        self.assertIsNone(sheet_score)
        self.assertIsNone(_intermediate_score(
            case,
            _route_score(case, None),
            _plan_score(case, decomposition),
            sheet_score,
        ))

    def test_pre_retrieval_scope_removes_search_and_reader_nodes(self) -> None:
        path = Path(__file__).parents[1] / "data" / "workflows" / "rag9_semantic_entry_hybrid.json"
        workflow = WorkflowDocument.model_validate(json.loads(path.read_text(encoding="utf-8")))
        scoped = _workflow_for_scope(workflow, "pre_retrieval")
        module_types = {node.module_type for node in scoped.graph.nodes}
        self.assertIn("semantic_query_matcher", module_types)
        self.assertIn("adaptive_query_decomposer", module_types)
        self.assertNotIn("bm25_retriever", module_types)
        self.assertNotIn("pgvector_retriever", module_types)
        self.assertNotIn("reader", module_types)
        node_ids = {node.id for node in scoped.graph.nodes}
        self.assertTrue(all(edge.source in node_ids and edge.target in node_ids for edge in scoped.graph.edges))


if __name__ == "__main__":
    unittest.main()
