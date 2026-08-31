"""Benchmark contracts, scoring rules, and workflow execution use case."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, Field, model_validator

from backend.core.settings import PROJECT_DIR
from backend.domains.workflow.application.dispatching import RunDispatcher
from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.application.ports import WorkflowDefinitionRepository
from backend.domains.workflow.domain import DagExecutionCancelled, DagExecutionError
from backend.domains.workflow.domain.models import (
    WorkflowDocument,
    WorkflowExecutionRequest,
)


@dataclass(frozen=True)
class PlanSignature:
    metrics: tuple[str, ...] = ()
    periods: tuple[int, ...] = ()


def plan_signature(subqueries: Sequence[Any]) -> PlanSignature:
    metrics: list[str] = []
    periods: list[int] = []
    for item in subqueries:
        text = str(item.get("query_text") if isinstance(item, dict) else item)
        for part in text.split():
            if part.isdigit() and len(part) == 4:
                try:
                    periods.append(int(part))
                except ValueError:
                    pass
            elif len(part) > 1:
                metrics.append(part)
    return PlanSignature(metrics=tuple(metrics), periods=tuple(periods))


class ExpectedPlan(BaseModel):
    metrics: List[str] = Field(default_factory=list)
    periods: List[int] = Field(default_factory=list)


class BenchmarkCase(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_numbers: List[float] = Field(default_factory=list)
    expected_terms: List[str] = Field(default_factory=list)
    expected_target: Optional[str] = None
    expected_sheets: Optional[List[str]] = None
    expected_abstain: bool = False
    expected_plan: Optional[ExpectedPlan] = None


class BenchmarkRequest(BaseModel):
    workflow_ids: List[str] = Field(min_length=2, max_length=12)
    cases: List[BenchmarkCase] = Field(min_length=1, max_length=200)
    use_cache: bool = False
    cache_mode: Literal["off", "all", "index_only"] = "off"
    execution_scope: Literal["full", "pre_retrieval"] = "full"

    @model_validator(mode="after")
    def require_unique_workflows_and_cases(self) -> "BenchmarkRequest":
        if len(self.workflow_ids) != len(set(self.workflow_ids)):
            raise ValueError("workflow_ids must be unique")
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case ids must be unique")
        return self


_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\(?\d[\d,]*(?:\.\d+)?\)?")
BENCHMARK_SET_DIR = PROJECT_DIR / "data" / "benchmark_sets"
BENCHMARK_SET_NAMES = {
    "semantic-decomposition-core-6": "6유형 핵심 6문항",
    "semantic-decomposition-holdout-18": "분해 홀드아웃 18문항",
    "semantic-routing-comparison-24": "라우팅 비교 24문항",
    "semantic-safety-holdout-30": "안전성 홀드아웃 30문항",
}
PRE_RETRIEVAL_MODULE_TYPES = {
    "query_input",
    "llm_query_router",
    "decomposer",
}


def _workflow_for_scope(
    workflow: WorkflowDocument,
    execution_scope: Literal["full", "pre_retrieval"],
) -> WorkflowDocument:
    """Create a run-only upstream graph without changing the saved workflow."""

    if execution_scope == "full":
        return workflow
    nodes = [
        node for node in workflow.graph.nodes if node.module_type in PRE_RETRIEVAL_MODULE_TYPES
    ]
    node_ids = {node.id for node in nodes}
    if not any(node.module_type == "decomposer" for node in nodes):
        raise ValueError(f"{workflow.id} has no decomposition node for pre-retrieval evaluation")
    graph = workflow.graph.model_copy(
        update={
            "nodes": nodes,
            "edges": [
                edge
                for edge in workflow.graph.edges
                if edge.source in node_ids and edge.target in node_ids
            ],
        }
    )
    return workflow.model_copy(update={"graph": graph})


def _seconds_between(started_at: Optional[str], completed_at: Optional[str]) -> Optional[float]:
    if not started_at or not completed_at:
        return None
    return max(
        0.0,
        (
            datetime.fromisoformat(completed_at).timestamp()
            - datetime.fromisoformat(started_at).timestamp()
        ),
    )


def _numbers(text: str) -> List[float]:
    values = []
    for raw in _NUMBER.findall(text):
        negative = raw.startswith("(") and raw.endswith(")")
        try:
            value = float(raw.strip("()").replace(",", ""))
            values.append(-value if negative else value)
        except ValueError:
            pass
    return values


def _matches(expected: float, values: List[float]) -> bool:
    return any(abs(expected - value) <= max(0.01, abs(expected) * 0.005) for value in values)


def _run_metrics(run: Any) -> Dict[str, Any]:
    node_rows = []
    total_tokens = 0
    estimated_cost = 0.0
    reused_tokens = 0
    reused_cost = 0.0
    cache_hits = 0
    llm_fallback_calls = 0
    plan_reused = None
    decomposition = None
    answer = ""
    router = None
    for state in run.nodes.values():
        # elapsed_ms is measured around the module work itself.  Unlike the
        # request wall clock it excludes time waiting for the executor lock.
        seconds = (state.elapsed_ms / 1000) if state.elapsed_ms is not None else None
        usage = state.usage or {}
        node_tokens = int(usage.get("total_tokens", 0) or 0)
        node_cost = float(state.cost_usd or 0)
        if state.cache_hit:
            # The cached output can contain the token/cost metadata from the
            # original call.  Keep it as a reference only; it was not billed
            # again during this benchmark run.
            cache_hits += 1
            reused_tokens += node_tokens
            reused_cost += node_cost
        else:
            total_tokens += node_tokens
            estimated_cost += node_cost
        output = state.output or {}
        if state.module_type == "decomposer":
            decomposer_output = state.output if isinstance(state.output, dict) else {}
            raw_subqueries = decomposer_output.get("items")
            decomposition = {
                "source": "llm_decomposer",
                "subqueries": [
                    item.get("text") if isinstance(item, dict) else str(item)
                    for item in raw_subqueries
                ]
                if isinstance(raw_subqueries, list)
                else [],
            }

        if isinstance(output, dict):
            candidate = output.get("answer_json")
            if isinstance(candidate, dict):
                answer = str(candidate.get("answer") or answer)
            match = output.get("semantic_match")
            if isinstance(match, dict):
                metrics = match.get("metrics") or {}
                usage = metrics.get("api_usage") or {}
                scopes = match.get("items") or []
                first_scope = scopes[0] if scopes and isinstance(scopes[0], dict) else {}
                router = {
                    "kind": str(metrics.get("kind") or "unknown"),
                    "target": first_scope.get("company_name"),
                    "sheets": list(
                        dict.fromkeys(
                            sheet
                            for scope in scopes
                            if isinstance(scope, dict)
                            for sheet in scope.get("sheets", [])
                        )
                    ),
                    "matched": bool(scopes),
                    "latency_seconds": float(metrics.get("latency_seconds", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                    "estimated_cost_usd": float(metrics.get("estimated_cost_usd", 0) or 0),
                }
            routes = output.get("routes")
            metrics = output.get("metrics")
            if isinstance(routes, list) and isinstance(metrics, dict):
                usage = metrics.get("api_usage") or {}
                first_route = routes[0] if routes and isinstance(routes[0], dict) else {}
                first_collections = first_route.get("collections") or []
                first_collection = (
                    first_collections[0]
                    if first_collections and isinstance(first_collections[0], dict)
                    else {}
                )
                router = {
                    "kind": str(metrics.get("kind") or "unknown"),
                    "target": first_collection.get("company_name"),
                    "sheets": list(
                        dict.fromkeys(
                            str(route.get("subquery", {}).get("sheet"))
                            for route in routes
                            if isinstance(route, dict)
                            and isinstance(route.get("subquery"), dict)
                            and route["subquery"].get("sheet") not in (None, "", "?")
                        )
                    ),
                    "matched": bool(routes),
                    "latency_seconds": float(metrics.get("latency_seconds", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                    "estimated_cost_usd": float(metrics.get("estimated_cost_usd", 0) or 0),
                }
        node_rows.append(
            {
                "node_id": state.node_id,
                "module_type": state.module_type,
                "status": state.status,
                "cache_hit": state.cache_hit,
                "latency_seconds": seconds,
            }
        )
    backend_seconds = sum(row["latency_seconds"] or 0 for row in node_rows)
    return {
        "run_id": run.id,
        "status": run.status,
        "latency_seconds": round(backend_seconds, 3),
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "reused_tokens": reused_tokens,
        "reused_cost_usd": round(reused_cost, 6),
        "cache_hits": cache_hits,
        "node_runs": len(node_rows),
        "llm_fallback_calls": llm_fallback_calls,
        "plan_reused": plan_reused,
        "decomposition": decomposition,
        "answer": answer,
        "router": router,
        "timeline": node_rows,
    }


def _preview_output(value: Any, limit: int = 900) -> str:
    """Return a bounded, UI-safe representation for live benchmark inspection."""
    if value is None:
        return ""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "\n… (출력 일부만 표시)"


def run_snapshot(run: Any) -> Dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "nodes": [
            {
                "node_id": state.node_id,
                "module_type": state.module_type,
                "status": state.status,
                "elapsed_ms": state.elapsed_ms,
                "cache_hit": state.cache_hit,
                "error": state.error,
                "output_preview": _preview_output(state.output),
            }
            for state in run.nodes.values()
        ],
    }


def _score(case: BenchmarkCase, answer: str) -> Dict[str, Any]:
    # Free-form, one-line inputs deliberately have no reference answer.  They
    # measure latency/cost only and must never be reported as 100% accurate.
    scored = bool(case.expected_numbers or case.expected_terms)
    values = _numbers(answer)
    number_ok = all(_matches(expected, values) for expected in case.expected_numbers)
    lowered = answer.lower()
    term_ok = all(term.lower() in lowered for term in case.expected_terms)
    return {
        "scored": scored,
        "correct": (bool(answer) and number_ok and term_ok) if scored else None,
        "matched_numbers": sum(_matches(expected, values) for expected in case.expected_numbers),
        "expected_numbers": len(case.expected_numbers),
        "matched_terms": sum(term.lower() in lowered for term in case.expected_terms),
        "expected_terms": len(case.expected_terms),
    }


def _route_score(case: BenchmarkCase, router: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Score routing only when the benchmark case includes route ground truth."""

    if case.expected_target is None and case.expected_sheets is None and not case.expected_abstain:
        return None
    if router is None:
        # Workflows without a router do not make a routing decision. Their
        # decomposition quality is measured separately, so they must not be
        # treated as a failed router on every labelled case.
        return None
    if case.expected_abstain:
        abstained = not bool(router.get("matched"))
        return {
            "correct": abstained,
            "target_correct": abstained,
            "sheets_correct": abstained,
            "expected_abstain": True,
        }
    target_correct = case.expected_target is None or router.get("target") == case.expected_target
    expected_sheets = {sheet.casefold() for sheet in case.expected_sheets or []}
    actual_sheets = {str(sheet).casefold() for sheet in router.get("sheets", [])}
    sheets_recall = (
        len(expected_sheets & actual_sheets) / len(expected_sheets) if expected_sheets else 1.0
    )
    sheets_precision = (
        len(expected_sheets & actual_sheets) / len(actual_sheets)
        if actual_sheets
        else (1.0 if not expected_sheets else 0.0)
    )
    sheets_exact = case.expected_sheets is None or actual_sheets == expected_sheets
    return {
        "correct": target_correct and sheets_exact,
        "target_correct": target_correct,
        "sheets_correct": sheets_exact,
        "sheets_exact": sheets_exact,
        "sheet_precision": sheets_precision,
        "sheet_recall": sheets_recall,
        "expected_abstain": False,
    }


def _plan_score(case: BenchmarkCase, decomposition: Any) -> Optional[Dict[str, Any]]:
    """Compare a produced retrieval plan with canonical holdout constraints."""

    if case.expected_plan is None:
        return None
    subqueries = decomposition.get("subqueries", []) if isinstance(decomposition, dict) else []
    signature = plan_signature(subqueries) if isinstance(subqueries, list) else None
    actual_metrics = set(signature.metrics) if signature else set()
    actual_periods = set(signature.periods) if signature else set()
    expected_metrics = set(case.expected_plan.metrics)
    expected_periods = set(case.expected_plan.periods)
    metric_overlap = expected_metrics & actual_metrics
    metric_recall = len(metric_overlap) / len(expected_metrics) if expected_metrics else 1.0
    metric_precision = (
        len(metric_overlap) / len(actual_metrics)
        if actual_metrics
        else (1.0 if not expected_metrics else 0.0)
    )
    metrics_correct = not expected_metrics or actual_metrics == expected_metrics
    periods_correct = not expected_periods or actual_periods == expected_periods
    return {
        "correct": signature is not None and metrics_correct and periods_correct,
        "metrics_correct": metrics_correct,
        "metric_precision": metric_precision,
        "metric_recall": metric_recall,
        "periods_correct": periods_correct,
        "expected_metrics": sorted(expected_metrics),
        "actual_metrics": sorted(actual_metrics),
        "expected_periods": sorted(expected_periods),
        "actual_periods": sorted(actual_periods),
        "source": decomposition.get("source") if isinstance(decomposition, dict) else None,
    }


def _sheet_score(
    case: BenchmarkCase,
    router: Any,
    decomposition: Any,
) -> Optional[Dict[str, Any]]:
    """Score concrete sheet selection from either a route or a structured plan."""

    if case.expected_sheets is None:
        return None
    expected = {sheet.casefold(): sheet for sheet in case.expected_sheets}
    # Sheet selection is a router decision. A normal LLM decomposition uses
    # Sheet: ? by design, and treating an occasional literal sheet name in a
    # plan as routing output makes baseline comparisons inconsistent.
    if router is None:
        return None
    actual_values = [str(sheet) for sheet in router.get("sheets", [])]
    actual = {sheet.casefold(): sheet for sheet in actual_values}
    overlap = set(expected) & set(actual)
    precision = len(overlap) / len(actual) if actual else 0.0
    recall = len(overlap) / len(expected) if expected else 1.0
    return {
        "correct": set(actual) == set(expected),
        "precision": precision,
        "recall": recall,
        "expected": sorted(expected.values(), key=str.casefold),
        "actual": sorted(actual.values(), key=str.casefold),
    }


def _intermediate_score(
    case: BenchmarkCase,
    route_score: Optional[Dict[str, Any]],
    plan_score: Optional[Dict[str, Any]],
    sheet_score: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Strictly combine every available pre-retrieval ground-truth constraint."""

    checks: Dict[str, bool] = {}
    if route_score is None and (case.expected_abstain or case.expected_sheets is not None):
        return None
    if case.expected_abstain:
        checks["abstention"] = bool(route_score and route_score["correct"])
    if case.expected_sheets is not None and sheet_score is None:
        # No concrete sheet decision was made (for example, an LLM plan with
        # Sheet: ?). Its plan quality is still reported separately, but it
        # cannot participate in a routing-and-plan composite score.
        return None
    if sheet_score is not None:
        checks["sheets"] = bool(sheet_score["correct"])
    if plan_score is not None:
        checks["plan"] = bool(plan_score["correct"])
    if not checks:
        return None
    return {"correct": all(checks.values()), "checks": checks}


def _cache_mode(request: BenchmarkRequest) -> str:
    return "all" if request.use_cache and request.cache_mode == "off" else request.cache_mode


def _progress(
    callback: Optional[Any],
    *,
    event: str,
    completed: int,
    total: int,
    case_index: int,
    case: BenchmarkCase,
    workflow_id: str,
    run_id: str | None,
    **extra: Any,
) -> None:
    if callback:
        callback(
            {
                "event": event,
                "completed": completed,
                "total": total,
                "case_index": case_index,
                "case_id": case.id,
                "question": case.question,
                "workflow_id": workflow_id,
                "run_id": run_id,
                **extra,
            }
        )


def _create_or_resume_run(
    request: BenchmarkRequest,
    case: BenchmarkCase,
    workflow: WorkflowDocument,
    query_node_id: str,
    workflow_executor: WorkflowExecutor,
    resume_run_id: str | None,
) -> Any:
    if resume_run_id is not None:
        return workflow_executor.run_store.load_summary(resume_run_id)
    cache_mode = _cache_mode(request)
    return workflow_executor.create_run(
        workflow,
        WorkflowExecutionRequest(
            inputs={query_node_id: {"query": case.question}},
            use_cache=cache_mode != "off",
            cache_only_module_types=["pgvector_data_scope"] if cache_mode == "index_only" else None,
        ),
    )


def _wait_for_benchmark_run(
    run: Any,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
) -> Any:
    deadline = time.monotonic() + 3600
    while True:
        summary = workflow_executor.run_store.load_summary(run.id)
        if summary.status in ("completed", "failed", "paused"):
            return workflow_executor.run_store.load(run.id)
        if time.monotonic() >= deadline:
            workflow_dispatcher.cancel(run.id)
            raise DagExecutionError(f"Kubernetes benchmark run timeout: {run.id}")
        time.sleep(0.5)


def _require_completed_run(run: Any) -> None:
    if run.status == "completed":
        return
    failed_node = next(
        (state for state in run.nodes.values() if state.status == "failed"),
        None,
    )
    raise DagExecutionError(
        failed_node.error
        if failed_node is not None and failed_node.error
        else f"Kubernetes benchmark run ended with {run.status}"
    )


def _unscored_answer(case: BenchmarkCase) -> Dict[str, Any]:
    return {
        "scored": False,
        "correct": None,
        "matched_numbers": 0,
        "expected_numbers": len(case.expected_numbers),
        "matched_terms": 0,
        "expected_terms": len(case.expected_terms),
    }


def _failed_answer_score(request: BenchmarkRequest, case: BenchmarkCase) -> Dict[str, Any]:
    has_expectations = bool(case.expected_numbers or case.expected_terms)
    should_score = request.execution_scope == "full" and has_expectations
    return {
        **_unscored_answer(case),
        "scored": should_score,
        "correct": False if should_score else None,
    }


def _score_case(
    request: BenchmarkRequest,
    case: BenchmarkCase,
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    score = (
        _score(case, metrics["answer"])
        if request.execution_scope == "full"
        else _unscored_answer(case)
    )
    route_score = _route_score(case, metrics["router"])
    plan_score = _plan_score(case, metrics["decomposition"])
    sheet_score = _sheet_score(case, metrics["router"], metrics["decomposition"])
    return {
        "score": score,
        "route_score": route_score,
        "plan_score": plan_score,
        "sheet_score": sheet_score,
        "intermediate_score": _intermediate_score(
            case,
            route_score,
            plan_score,
            sheet_score,
        ),
    }


def _empty_run_metrics() -> Dict[str, Any]:
    return {
        "run_id": None,
        "status": "failed",
        "latency_seconds": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0,
        "reused_tokens": 0,
        "reused_cost_usd": 0,
        "cache_hits": 0,
        "node_runs": 0,
        "llm_fallback_calls": 0,
        "plan_reused": None,
        "decomposition": None,
        "answer": "",
        "router": None,
        "timeline": [],
    }


def _failed_case_row(
    request: BenchmarkRequest,
    case: BenchmarkCase,
    workflow_id: str,
    run: Any,
    error: Exception,
) -> Dict[str, Any]:
    metrics = _run_metrics(run) if run is not None else _empty_run_metrics()
    scores = _score_case(request, case, metrics)
    scores["score"] = _failed_answer_score(request, case)
    return {
        "workflow_id": workflow_id,
        "case_id": case.id,
        "question": case.question,
        **metrics,
        **scores,
        "error": str(error),
    }


def _execute_case(
    request: BenchmarkRequest,
    case: BenchmarkCase,
    workflow_id: str,
    workflow: WorkflowDocument,
    query_node_id: str,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
    *,
    resume_run_id: str | None,
    await_permission: Optional[Any],
    on_running: Optional[Any],
) -> tuple[Dict[str, Any], Any]:
    run = None
    try:
        if await_permission:
            await_permission()
        run = _create_or_resume_run(
            request,
            case,
            workflow,
            query_node_id,
            workflow_executor,
            resume_run_id,
        )
        if on_running:
            on_running(run.id)
        if resume_run_id is None:
            workflow_dispatcher.submit(run.id)
        run = _wait_for_benchmark_run(run, workflow_executor, workflow_dispatcher)
        _require_completed_run(run)
        metrics = _run_metrics(run)
        return (
            {
                "workflow_id": workflow_id,
                "case_id": case.id,
                "question": case.question,
                **metrics,
                **_score_case(request, case, metrics),
                "error": None,
            },
            run,
        )
    except DagExecutionCancelled:
        raise
    except (DagExecutionError, ValueError) as error:
        return _failed_case_row(request, case, workflow_id, run, error), run


def _answer_summary(group: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [row for row in group if row["score"]["scored"]]
    return {
        "scored_cases": len(scored),
        "accuracy": round(sum(bool(row["score"]["correct"]) for row in scored) / len(scored), 4)
        if scored
        else None,
    }


def _resource_summary(group: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "average_latency_seconds": round(mean(row["latency_seconds"] for row in group), 3),
        "average_tokens": round(mean(row["total_tokens"] for row in group), 1),
        "average_cost_usd": round(mean(row["estimated_cost_usd"] for row in group), 6),
        "average_reused_tokens": round(mean(row["reused_tokens"] for row in group), 1),
        "average_reused_cost_usd": round(mean(row["reused_cost_usd"] for row in group), 6),
        "cache_hits": sum(row["cache_hits"] for row in group),
        "node_runs": sum(row["node_runs"] for row in group),
        "llm_fallback_calls": sum(row["llm_fallback_calls"] for row in group),
        "errors": sum(row["error"] is not None for row in group),
    }


def _plan_summary(group: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    decisions = [row for row in group if row["plan_reused"] is not None]
    planned = [row for row in group if row["plan_score"] is not None]
    reused = [row for row in planned if row["plan_reused"] is True]
    return {
        "plan_reuse_count": sum(row["plan_reused"] is True for row in decisions),
        "plan_reuse_coverage": round(
            sum(row["plan_reused"] is True for row in decisions) / len(decisions), 4
        )
        if decisions
        else None,
        "plan_cases": len(planned),
        "plan_accuracy": round(
            sum(row["plan_score"]["correct"] for row in planned) / len(planned), 4
        )
        if planned
        else None,
        "plan_reuse_precision": round(
            sum(row["plan_score"]["correct"] for row in reused) / len(reused), 4
        )
        if reused
        else None,
        "unsafe_plan_reuse_count": sum(not row["plan_score"]["correct"] for row in reused),
    }


def _sheet_summary(group: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [row for row in group if row["sheet_score"] is not None]
    return {
        "sheet_cases": len(rows),
        "sheet_exact_accuracy": round(
            sum(row["sheet_score"]["correct"] for row in rows) / len(rows), 4
        )
        if rows
        else None,
        "average_sheet_precision": round(mean(row["sheet_score"]["precision"] for row in rows), 4)
        if rows
        else None,
        "average_sheet_recall": round(mean(row["sheet_score"]["recall"] for row in rows), 4)
        if rows
        else None,
    }


def _intermediate_summary(group: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [row for row in group if row["intermediate_score"] is not None]
    return {
        "intermediate_cases": len(rows),
        "intermediate_accuracy": round(
            sum(row["intermediate_score"]["correct"] for row in rows) / len(rows), 4
        )
        if rows
        else None,
    }


def _route_summary(group: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    routed = [row for row in group if row["route_score"] is not None]
    router_rows = [row for row in group if row["router"] is not None]
    attempts = [row for row in routed if row["router"] and row["router"].get("matched")]
    positives = [row for row in routed if not row["route_score"]["expected_abstain"]]
    positive_attempts = [row for row in positives if row["router"] and row["router"].get("matched")]
    abstentions = [row for row in routed if row["route_score"]["expected_abstain"]]
    return {
        "route_cases": len(routed),
        "route_accuracy": round(
            sum(row["route_score"]["correct"] for row in routed) / len(routed), 4
        )
        if routed
        else None,
        "route_attempts": len(attempts),
        "route_abstentions": len(routed) - len(attempts),
        "route_coverage": round(len(positive_attempts) / len(positives), 4) if positives else None,
        "route_precision": round(
            sum(row["route_score"]["correct"] for row in attempts) / len(attempts), 4
        )
        if attempts
        else None,
        "abstention_cases": len(abstentions),
        "abstention_accuracy": round(
            sum(row["route_score"]["correct"] for row in abstentions) / len(abstentions), 4
        )
        if abstentions
        else None,
        **_router_resource_summary(router_rows),
    }


def _router_resource_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "router_kind": rows[0]["router"]["kind"] if rows else None,
        "average_router_latency_seconds": round(
            mean(row["router"]["latency_seconds"] for row in rows), 3
        )
        if rows
        else None,
        "average_router_tokens": round(mean(row["router"]["total_tokens"] for row in rows), 1)
        if rows
        else None,
        "average_router_cost_usd": round(
            mean(row["router"]["estimated_cost_usd"] for row in rows), 6
        )
        if rows
        else None,
    }


def _benchmark_summary(
    request: BenchmarkRequest,
    rows: Sequence[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    summary: list[Dict[str, Any]] = []
    for workflow_id in request.workflow_ids:
        group = [row for row in rows if row["workflow_id"] == workflow_id]
        summary.append(
            {
                "workflow_id": workflow_id,
                "cases": len(group),
                **_answer_summary(group),
                **_resource_summary(group),
                **_plan_summary(group),
                **_sheet_summary(group),
                **_intermediate_summary(group),
                **_route_summary(group),
            }
        )
    return summary


def execute_benchmark_comparison(
    request: BenchmarkRequest,
    workflow_store: WorkflowDefinitionRepository,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
    on_progress: Optional[Any] = None,
    await_permission: Optional[Any] = None,
    initial_rows: Sequence[Dict[str, Any]] = (),
    resume_active: Optional[tuple[str, str, str]] = None,
) -> Dict[str, Any]:
    """Run a comparison and report each case/workflow transition to the caller."""
    workflows = validate_workflows(request, workflow_store)
    rows = list(initial_rows)
    completed_identities = {(str(row.get("workflow_id")), str(row.get("case_id"))) for row in rows}
    completed = len(rows)
    total = len(request.cases) * len(workflows)
    for case_index, case in enumerate(request.cases):
        for workflow_id, (workflow, query_node_id) in workflows.items():
            if (workflow_id, case.id) in completed_identities:
                continue
            run = None
            resuming = resume_active is not None and resume_active[:2] == (
                workflow_id,
                case.id,
            )
            resume_run_id = resume_active[2] if resuming and resume_active else None
            _progress(
                on_progress,
                event="started",
                completed=completed,
                total=total,
                case_index=case_index,
                case=case,
                workflow_id=workflow_id,
                run_id=resume_run_id,
            )
            row, run = _execute_case(
                request,
                case,
                workflow_id,
                workflow,
                query_node_id,
                workflow_executor,
                workflow_dispatcher,
                resume_run_id=resume_run_id,
                await_permission=await_permission,
                on_running=lambda run_id, completed=completed, case_index=case_index, case=case, workflow_id=workflow_id: (
                    _progress(
                        on_progress,
                        event="running",
                        completed=completed,
                        total=total,
                        case_index=case_index,
                        case=case,
                        workflow_id=workflow_id,
                        run_id=run_id,
                    )
                ),
            )
            rows.append(row)
            completed += 1
            _progress(
                on_progress,
                event="completed",
                completed=completed,
                total=total,
                case_index=case_index,
                case=case,
                workflow_id=workflow_id,
                run_id=None,
                error=row["error"],
                run=run_snapshot(run) if run else None,
                result_row=row,
            )

    cache_mode = _cache_mode(request)
    return {
        "execution_mode": "sequential_isolated",
        "execution_scope": request.execution_scope,
        "use_cache": cache_mode != "off",
        "cache_mode": cache_mode,
        "summary": _benchmark_summary(request, rows),
        "results": rows,
    }


def validate_workflows(
    request: BenchmarkRequest,
    workflow_store: WorkflowDefinitionRepository,
) -> Dict[str, tuple[WorkflowDocument, str]]:
    workflows = {}
    for workflow_id in request.workflow_ids:
        try:
            workflow = workflow_store.load(workflow_id)
        except FileNotFoundError as error:
            raise FileNotFoundError(f"Workflow not found: {workflow_id}") from error
        query_nodes = [node for node in workflow.graph.nodes if node.module_type == "query_input"]
        if len(query_nodes) != 1:
            raise ValueError(f"{workflow_id} must contain exactly one query_input node")
        scoped_workflow = _workflow_for_scope(workflow, request.execution_scope)
        workflows[workflow_id] = (scoped_workflow, query_nodes[0].id)

    return workflows


__all__ = [
    "BENCHMARK_SET_DIR",
    "BENCHMARK_SET_NAMES",
    "BenchmarkCase",
    "BenchmarkRequest",
    "execute_benchmark_comparison",
    "run_snapshot",
    "validate_workflows",
]
