"""Repeatable, fair end-to-end RAG benchmark endpoints."""

from __future__ import annotations

import re
import json
from threading import Event, Lock, Thread
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..workflows import DagExecutionCancelled, DagExecutionError, WorkflowDocument, WorkflowExecutionRequest, WorkflowExecutor, WorkflowStore
from ..core.settings import BENCHMARK_DIR, PROJECT_DIR
from ..semantic_matching.plan_validation import plan_signature


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
    "semantic_query_matcher",
    "llm_query_router",
    "decomposer",
    "adaptive_query_decomposer",
    "template_query_decomposer",
    "direct_query_decomposer",
}


def _workflow_for_scope(
    workflow: WorkflowDocument,
    execution_scope: Literal["full", "pre_retrieval"],
) -> WorkflowDocument:
    """Create a run-only upstream graph without changing the saved workflow."""

    if execution_scope == "full":
        return workflow
    nodes = [
        node for node in workflow.graph.nodes
        if node.module_type in PRE_RETRIEVAL_MODULE_TYPES
    ]
    node_ids = {node.id for node in nodes}
    if not any(
        node.module_type in {"decomposer", "adaptive_query_decomposer", "template_query_decomposer", "direct_query_decomposer"}
        for node in nodes
    ):
        raise ValueError(f"{workflow.id} has no decomposition node for pre-retrieval evaluation")
    graph = workflow.graph.model_copy(update={
        "nodes": nodes,
        "edges": [
            edge for edge in workflow.graph.edges
            if edge.source in node_ids and edge.target in node_ids
        ],
    })
    return workflow.model_copy(update={"graph": graph})


def _seconds_between(started_at: Optional[str], completed_at: Optional[str]) -> Optional[float]:
    if not started_at or not completed_at:
        return None
    return max(0.0, (datetime.fromisoformat(completed_at).timestamp() - datetime.fromisoformat(started_at).timestamp()))


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
            raw_subqueries = decomposer_output.get("subqueries")
            decomposition = {
                "source": "llm_decomposer",
                "subqueries": list(raw_subqueries) if isinstance(raw_subqueries, list) else [],
            }

        # AdaptiveQueryDecomposer can fall back for route failure, low plan
        # confidence, a missing plan, or a constraint mismatch. Usage is the
        # authoritative signal for new runs; the matched flag keeps old saved
        # runs interpretable.
        if state.module_type in {"adaptive_query_decomposer", "template_query_decomposer"} and isinstance(state.input_payload, dict):
            semantic_match = state.input_payload.get("semantic_match")
            used_llm = state.usage is not None or (
                isinstance(semantic_match, dict)
                and semantic_match.get("matched") is False
            )
            if used_llm:
                llm_fallback_calls += 1
            if not state.cache_hit:
                plan_reused = not used_llm
            adaptive_output = state.output if isinstance(state.output, dict) else {}
            raw_subqueries = adaptive_output.get("subqueries")
            decomposition = {
                "source": (
                    "cache_unknown" if state.cache_hit
                    else "llm_fallback" if used_llm
                    else (
                        "template_reuse"
                        if state.module_type == "template_query_decomposer"
                        else "semantic_reuse"
                    )
                ),
                "subqueries": list(raw_subqueries) if isinstance(raw_subqueries, list) else [],
            }
        if isinstance(output, dict):
            candidate = output.get("answer_json")
            if isinstance(candidate, dict):
                answer = str(candidate.get("answer") or answer)
            match = output.get("semantic_match")
            if isinstance(match, dict):
                metrics = match.get("metrics") or {}
                usage = metrics.get("api_usage") or {}
                router = {
                    "kind": str(metrics.get("kind") or "unknown"),
                    "target": match.get("target"),
                    "sheets": list(match.get("sheets") or []),
                    "matched": bool(match.get("matched")),
                    "latency_seconds": float(metrics.get("latency_seconds", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                    "estimated_cost_usd": float(metrics.get("estimated_cost_usd", 0) or 0),
                }
        node_rows.append({
            "node_id": state.node_id,
            "module_type": state.module_type,
            "status": state.status,
            "cache_hit": state.cache_hit,
            "latency_seconds": seconds,
        })
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


def _run_snapshot(run: Any) -> Dict[str, Any]:
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
        len(expected_sheets & actual_sheets) / len(expected_sheets)
        if expected_sheets else 1.0
    )
    sheets_precision = (
        len(expected_sheets & actual_sheets) / len(actual_sheets)
        if actual_sheets else (1.0 if not expected_sheets else 0.0)
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


def _plan_score(case: BenchmarkCase, decomposition: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Compare a produced retrieval plan with canonical holdout constraints."""

    if case.expected_plan is None:
        return None
    subqueries = decomposition.get("subqueries", []) if decomposition else []
    signature = plan_signature(subqueries) if isinstance(subqueries, list) else None
    actual_metrics = set(signature.metrics) if signature else set()
    actual_periods = set(signature.periods) if signature else set()
    expected_metrics = set(case.expected_plan.metrics)
    expected_periods = set(case.expected_plan.periods)
    metric_overlap = expected_metrics & actual_metrics
    metric_recall = len(metric_overlap) / len(expected_metrics) if expected_metrics else 1.0
    metric_precision = len(metric_overlap) / len(actual_metrics) if actual_metrics else (1.0 if not expected_metrics else 0.0)
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
        "source": decomposition.get("source") if decomposition else None,
    }


def _sheet_score(
    case: BenchmarkCase,
    router: Optional[Dict[str, Any]],
    decomposition: Optional[Dict[str, Any]],
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


def _save_benchmark(result: Dict[str, Any]) -> Dict[str, Any]:
    """Persist comparison output separately from the per-workflow run history."""

    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    benchmark_id = f"benchmark-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    record = {"id": benchmark_id, "saved_at": datetime.now().astimezone().isoformat(), **result}
    path = BENCHMARK_DIR / f"{benchmark_id}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return record


def _list_benchmarks() -> List[Dict[str, Any]]:
    if not BENCHMARK_DIR.exists():
        return []
    records = []
    for path in sorted(BENCHMARK_DIR.glob("benchmark-*.json"), reverse=True):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            records.append({"id": item["id"], "saved_at": item["saved_at"], "summary": item.get("summary", [])})
        except (OSError, ValueError, KeyError):
            continue
    return records


def _execute_comparison(
    request: BenchmarkRequest,
    workflow_store: WorkflowStore,
    workflow_executor: WorkflowExecutor,
    on_progress: Optional[Any] = None,
    await_permission: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run a comparison and report each case/workflow transition to the caller."""
    workflows = {}
    for workflow_id in request.workflow_ids:
        try:
            workflow = workflow_store.load(workflow_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from error
        query_nodes = [node for node in workflow.graph.nodes if node.module_type == "query_input"]
        if len(query_nodes) != 1:
            raise HTTPException(status_code=422, detail=f"{workflow_id} must contain exactly one query_input node")
        scoped_workflow = _workflow_for_scope(workflow, request.execution_scope)
        workflows[workflow_id] = (scoped_workflow, query_nodes[0].id)

    rows = []
    completed = 0
    total = len(request.cases) * len(workflows)
    for case_index, case in enumerate(request.cases):
        for workflow_id, (workflow, query_node_id) in workflows.items():
            run = None
            try:
                if await_permission:
                    await_permission()
                if on_progress:
                    on_progress({"event": "started", "completed": completed, "total": total, "case_index": case_index, "case_id": case.id, "question": case.question, "workflow_id": workflow_id, "run_id": None})
                cache_mode = "all" if request.use_cache and request.cache_mode == "off" else request.cache_mode
                run = workflow_executor.create_run(workflow, WorkflowExecutionRequest(
                    inputs={query_node_id: {"query": case.question}},
                    use_cache=cache_mode != "off",
                    cache_only_module_types=["prebuilt_index_loader", "pgvector_collection_loader"] if cache_mode == "index_only" else None,
                ))
                if on_progress:
                    on_progress({"event": "running", "completed": completed, "total": total, "case_index": case_index, "case_id": case.id, "question": case.question, "workflow_id": workflow_id, "run_id": run.id})
                run = workflow_executor.execute_all(run.id)
                metrics = _run_metrics(run)
                score = (
                    _score(case, metrics["answer"])
                    if request.execution_scope == "full"
                    else {"scored": False, "correct": None, "matched_numbers": 0, "expected_numbers": len(case.expected_numbers), "matched_terms": 0, "expected_terms": len(case.expected_terms)}
                )
                route_score = _route_score(case, metrics["router"])
                plan_score = _plan_score(case, metrics["decomposition"])
                sheet_score = _sheet_score(case, metrics["router"], metrics["decomposition"])
                intermediate_score = _intermediate_score(case, route_score, plan_score, sheet_score)
                error = None
            except DagExecutionCancelled:
                # A cancelled comparison must not continue with the next item.
                raise
            except (DagExecutionError, ValueError) as exc:
                metrics = _run_metrics(run) if run is not None else {"run_id": None, "status": "failed", "latency_seconds": 0, "total_tokens": 0, "estimated_cost_usd": 0, "reused_tokens": 0, "reused_cost_usd": 0, "cache_hits": 0, "node_runs": 0, "llm_fallback_calls": 0, "plan_reused": None, "decomposition": None, "answer": "", "router": None, "timeline": []}
                score = {
                    "scored": request.execution_scope == "full" and bool(case.expected_numbers or case.expected_terms),
                    "correct": False if request.execution_scope == "full" and (case.expected_numbers or case.expected_terms) else None,
                    "matched_numbers": 0,
                    "expected_numbers": len(case.expected_numbers),
                    "matched_terms": 0,
                    "expected_terms": len(case.expected_terms),
                }
                route_score = _route_score(case, None)
                plan_score = _plan_score(case, metrics["decomposition"])
                sheet_score = _sheet_score(case, metrics["router"], metrics["decomposition"])
                intermediate_score = _intermediate_score(case, route_score, plan_score, sheet_score)
                error = str(exc)
            rows.append({"workflow_id": workflow_id, "case_id": case.id, "question": case.question, **metrics, "score": score, "route_score": route_score, "plan_score": plan_score, "sheet_score": sheet_score, "intermediate_score": intermediate_score, "error": error})
            completed += 1
            if on_progress:
                on_progress({"event": "completed", "completed": completed, "total": total, "case_index": case_index, "case_id": case.id, "question": case.question, "workflow_id": workflow_id, "run_id": None, "error": error, "run": _run_snapshot(run) if run else None})

    summary = []
    for workflow_id in request.workflow_ids:
        group = [row for row in rows if row["workflow_id"] == workflow_id]
        scored = [row for row in group if row["score"]["scored"]]
        routed = [row for row in group if row["route_score"] is not None]
        router_rows = [row for row in group if row["router"] is not None]
        route_attempts = [
            row for row in routed
            if row["router"] is not None and row["router"].get("matched")
        ]
        positive_routes = [row for row in routed if not row["route_score"]["expected_abstain"]]
        positive_route_attempts = [
            row for row in positive_routes
            if row["router"] is not None and row["router"].get("matched")
        ]
        abstention_rows = [row for row in routed if row["route_score"]["expected_abstain"]]
        known_plan_decisions = [row for row in group if row["plan_reused"] is not None]
        planned = [row for row in group if row["plan_score"] is not None]
        reused_plans = [row for row in planned if row["plan_reused"] is True]
        sheet_rows = [row for row in group if row["sheet_score"] is not None]
        intermediate_rows = [row for row in group if row["intermediate_score"] is not None]
        summary.append({
            "workflow_id": workflow_id, "cases": len(group), "scored_cases": len(scored),
            "accuracy": round(sum(bool(row["score"]["correct"]) for row in scored) / len(scored), 4) if scored else None,
            "average_latency_seconds": round(mean(row["latency_seconds"] for row in group), 3),
            "average_tokens": round(mean(row["total_tokens"] for row in group), 1),
            "average_cost_usd": round(mean(row["estimated_cost_usd"] for row in group), 6),
            "average_reused_tokens": round(mean(row["reused_tokens"] for row in group), 1),
            "average_reused_cost_usd": round(mean(row["reused_cost_usd"] for row in group), 6),
            "cache_hits": sum(row["cache_hits"] for row in group),
            "node_runs": sum(row["node_runs"] for row in group),
            "llm_fallback_calls": sum(row["llm_fallback_calls"] for row in group),
            "plan_reuse_count": sum(row["plan_reused"] is True for row in known_plan_decisions),
            "plan_reuse_coverage": round(
                sum(row["plan_reused"] is True for row in known_plan_decisions) / len(known_plan_decisions), 4
            ) if known_plan_decisions else None,
            "plan_cases": len(planned),
            "plan_accuracy": round(
                sum(row["plan_score"]["correct"] for row in planned) / len(planned), 4
            ) if planned else None,
            "plan_reuse_precision": round(
                sum(row["plan_score"]["correct"] for row in reused_plans) / len(reused_plans), 4
            ) if reused_plans else None,
            "unsafe_plan_reuse_count": sum(
                not row["plan_score"]["correct"] for row in reused_plans
            ),
            "sheet_cases": len(sheet_rows),
            "sheet_exact_accuracy": round(
                sum(row["sheet_score"]["correct"] for row in sheet_rows) / len(sheet_rows), 4
            ) if sheet_rows else None,
            "average_sheet_precision": round(
                mean(row["sheet_score"]["precision"] for row in sheet_rows), 4
            ) if sheet_rows else None,
            "average_sheet_recall": round(
                mean(row["sheet_score"]["recall"] for row in sheet_rows), 4
            ) if sheet_rows else None,
            "intermediate_cases": len(intermediate_rows),
            "intermediate_accuracy": round(
                sum(row["intermediate_score"]["correct"] for row in intermediate_rows) / len(intermediate_rows), 4
            ) if intermediate_rows else None,
            "errors": sum(row["error"] is not None for row in group), "route_cases": len(routed),
            "route_accuracy": round(sum(row["route_score"]["correct"] for row in routed) / len(routed), 4) if routed else None,
            "route_attempts": len(route_attempts),
            "route_abstentions": len(routed) - len(route_attempts),
            "route_coverage": round(
                len(positive_route_attempts) / len(positive_routes), 4
            ) if positive_routes else None,
            "route_precision": round(
                sum(row["route_score"]["correct"] for row in route_attempts) / len(route_attempts), 4
            ) if route_attempts else None,
            "abstention_cases": len(abstention_rows),
            "abstention_accuracy": round(
                sum(row["route_score"]["correct"] for row in abstention_rows) / len(abstention_rows), 4
            ) if abstention_rows else None,
            "router_kind": router_rows[0]["router"]["kind"] if router_rows else None,
            "average_router_latency_seconds": round(mean(row["router"]["latency_seconds"] for row in router_rows), 3) if router_rows else None,
            "average_router_tokens": round(mean(row["router"]["total_tokens"] for row in router_rows), 1) if router_rows else None,
            "average_router_cost_usd": round(mean(row["router"]["estimated_cost_usd"] for row in router_rows), 6) if router_rows else None,
        })
    cache_mode = "all" if request.use_cache and request.cache_mode == "off" else request.cache_mode
    return _save_benchmark({"execution_mode": "sequential_isolated", "execution_scope": request.execution_scope, "use_cache": cache_mode != "off", "cache_mode": cache_mode, "summary": summary, "results": rows})


def create_benchmark_router(workflow_store: WorkflowStore, workflow_executor: WorkflowExecutor) -> APIRouter:
    router = APIRouter()
    jobs: Dict[str, Dict[str, Any]] = {}
    jobs_lock = Lock()

    @router.get("/benchmark-sets")
    def list_benchmark_sets():
        """Return checked-in benchmark cases validated against the live schema."""

        sets = []
        for path in sorted(BENCHMARK_SET_DIR.glob("*.json")):
            try:
                raw_cases = json.loads(path.read_text(encoding="utf-8"))
                cases = [BenchmarkCase.model_validate(item) for item in raw_cases]
            except (OSError, ValueError, TypeError) as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Invalid benchmark set {path.name}: {error}",
                ) from error
            sets.append({
                "id": path.stem,
                "name": BENCHMARK_SET_NAMES.get(path.stem, path.stem),
                "cases": [case.model_dump(mode="json", exclude_none=True) for case in cases],
            })
        return {"benchmark_sets": sets}

    @router.post("/benchmarks/compare")
    def compare_workflows(request: BenchmarkRequest):
        """Run workflows sequentially and return chart-ready accuracy/cost/timing data.

        Sequential execution is intentional: it measures single-request latency
        without one candidate stealing another candidate's API/CPU capacity.
        """
        return _execute_comparison(request, workflow_store, workflow_executor)

    @router.post("/benchmarks/jobs")
    def start_benchmark_job(request: BenchmarkRequest):
        """Start a comparison in the background so the UI can display live progress."""
        job_id = f"benchmark-job-{uuid4().hex}"
        resume_event = Event()
        resume_event.set()
        with jobs_lock:
            jobs[job_id] = {"id": job_id, "status": "queued", "completed": 0, "total": len(request.cases) * len(request.workflow_ids), "current": None, "logs": [], "active_run_id": None, "last_run": None, "cancel_requested": False, "pause_requested": False, "resume_event": resume_event, "result": None, "error": None}

        def wait_until_runnable() -> None:
            """Pause safely between workflow runs, never halfway through a node."""

            announced = False
            while True:
                with jobs_lock:
                    job = jobs[job_id]
                    if job["cancel_requested"]:
                        raise DagExecutionCancelled("벤치마크 실행이 중지되었습니다")
                    if not job["pause_requested"]:
                        if announced:
                            job["status"] = "running"
                        return
                    job["status"] = "paused"
                    if not announced:
                        job["logs"].append({"at": datetime.now().astimezone().isoformat(), "event": "paused", "completed": job["completed"], "total": job["total"]})
                        announced = True
                resume_event.wait(timeout=0.25)

        def update(progress: Dict[str, Any]) -> None:
            with jobs_lock:
                job = jobs[job_id]
                if job["cancel_requested"]:
                    raise DagExecutionCancelled("벤치마크 실행이 중지되었습니다")
                job["status"] = "pausing" if job["pause_requested"] else "running"
                job["completed"] = progress["completed"]
                job["total"] = progress["total"]
                job["current"] = {key: progress.get(key) for key in ("workflow_id", "case_id", "question", "run_id")}
                job["active_run_id"] = progress.get("run_id")
                if progress.get("run") is not None:
                    job["last_run"] = progress["run"]
                job["logs"].append({"at": datetime.now().astimezone().isoformat(), **progress})
                job["logs"] = job["logs"][-80:]

        def work() -> None:
            try:
                result = _execute_comparison(
                    request,
                    workflow_store,
                    workflow_executor,
                    update,
                    wait_until_runnable,
                )
                with jobs_lock:
                    jobs[job_id].update(status="completed", completed=jobs[job_id]["total"], active_run_id=None, result=result)
            except DagExecutionCancelled:
                with jobs_lock:
                    jobs[job_id].update(status="cancelled", active_run_id=None)
            except Exception as error:
                with jobs_lock:
                    jobs[job_id].update(status="failed", active_run_id=None, error=str(error))

        Thread(target=work, name=job_id, daemon=True).start()
        return {"id": job_id}

    @router.get("/benchmarks/jobs/{job_id}")
    def get_benchmark_job(job_id: str):
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Benchmark job not found")
            payload = {key: value for key, value in job.items() if key not in {"active_run_id", "cancel_requested", "pause_requested", "resume_event"}}
            active_run_id = job.get("active_run_id")
        if active_run_id:
            try:
                payload["active_run"] = _run_snapshot(workflow_executor.run_store.load(active_run_id))
            # On Windows the run store atomically replaces this file while a
            # node state changes.  A polling request can briefly observe the
            # file lock; keep the benchmark job healthy and retry next poll.
            except (FileNotFoundError, PermissionError, OSError, ValueError):
                payload["active_run"] = None
        else:
            payload["active_run"] = None
        return payload

    @router.delete("/benchmarks/jobs/{job_id}")
    def cancel_benchmark_job(job_id: str):
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Benchmark job not found")
            run_id = job.get("active_run_id")
            job["cancel_requested"] = True
            job["resume_event"].set()
            job["status"] = "cancelling"
            job["logs"].append({"at": datetime.now().astimezone().isoformat(), "event": "cancelling", "completed": job["completed"], "total": job["total"]})
        if run_id:
            workflow_executor.cancel_run(run_id)
        return {"id": job_id, "status": "cancelling"}

    @router.post("/benchmarks/jobs/{job_id}/pause")
    def pause_benchmark_job(job_id: str):
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Benchmark job not found")
            if job["status"] in {"completed", "cancelled", "failed", "cancelling"}:
                raise HTTPException(status_code=409, detail="Benchmark job cannot be paused")
            job["pause_requested"] = True
            job["resume_event"].clear()
            job["status"] = "pausing" if job.get("active_run_id") else "paused"
            job["logs"].append({"at": datetime.now().astimezone().isoformat(), "event": "pausing", "completed": job["completed"], "total": job["total"]})
            status = job["status"]
        return {"id": job_id, "status": status}

    @router.post("/benchmarks/jobs/{job_id}/resume")
    def resume_benchmark_job(job_id: str):
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Benchmark job not found")
            if job["status"] not in {"paused", "pausing"}:
                raise HTTPException(status_code=409, detail="Benchmark job is not paused")
            job["pause_requested"] = False
            job["status"] = "running"
            job["logs"].append({"at": datetime.now().astimezone().isoformat(), "event": "resumed", "completed": job["completed"], "total": job["total"]})
            job["resume_event"].set()
        return {"id": job_id, "status": "running"}

    @router.get("/benchmarks")
    def list_benchmarks():
        return {"benchmarks": _list_benchmarks()}

    @router.get("/benchmarks/{benchmark_id}")
    def get_benchmark(benchmark_id: str):
        path = BENCHMARK_DIR / f"{benchmark_id}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Benchmark result not found")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=500, detail="Benchmark result is unreadable") from error

    return router
