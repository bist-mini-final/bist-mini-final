"""Repeatable, fair end-to-end RAG benchmark endpoints."""

from __future__ import annotations

import re
from datetime import datetime
from statistics import mean
from time import perf_counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..workflows import DagExecutionCancelled, DagExecutionError, WorkflowExecutionRequest, WorkflowExecutor, WorkflowStore


class BenchmarkCase(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_numbers: List[float] = Field(default_factory=list)
    expected_terms: List[str] = Field(default_factory=list)


class BenchmarkRequest(BaseModel):
    workflow_ids: List[str] = Field(min_length=2, max_length=12)
    cases: List[BenchmarkCase] = Field(min_length=1, max_length=200)
    use_cache: bool = False


_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\(?\d[\d,]*(?:\.\d+)?\)?")


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
    answer = ""
    for state in run.nodes.values():
        seconds = _seconds_between(state.started_at, state.completed_at)
        output = state.output or {}
        if isinstance(output, dict):
            candidate = output.get("answer_json")
            if isinstance(candidate, dict):
                answer = str(candidate.get("answer") or answer)
                usage = candidate.get("api_usage") or {}
                total_tokens += int(usage.get("total_tokens", 0) or 0)
                estimated_cost += float(candidate.get("estimated_cost_usd", 0) or 0)
            match = output.get("semantic_match")
            if isinstance(match, dict):
                metrics = match.get("metrics") or {}
                usage = metrics.get("api_usage") or {}
                total_tokens += int(usage.get("total_tokens", 0) or 0)
                estimated_cost += float(metrics.get("estimated_cost_usd", 0) or 0)
        node_rows.append({
            "node_id": state.node_id,
            "module_type": state.module_type,
            "status": state.status,
            "cache_hit": state.cache_hit,
            "latency_seconds": seconds,
        })
    whole_run = _seconds_between(run.created_at, run.updated_at)
    return {
        "run_id": run.id,
        "status": run.status,
        "latency_seconds": whole_run,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "answer": answer,
        "timeline": node_rows,
    }


def _score(case: BenchmarkCase, answer: str) -> Dict[str, Any]:
    values = _numbers(answer)
    number_ok = all(_matches(expected, values) for expected in case.expected_numbers)
    lowered = answer.lower()
    term_ok = all(term.lower() in lowered for term in case.expected_terms)
    return {
        "correct": bool(answer) and number_ok and term_ok,
        "matched_numbers": sum(_matches(expected, values) for expected in case.expected_numbers),
        "expected_numbers": len(case.expected_numbers),
        "matched_terms": sum(term.lower() in lowered for term in case.expected_terms),
        "expected_terms": len(case.expected_terms),
    }


def create_benchmark_router(workflow_store: WorkflowStore, workflow_executor: WorkflowExecutor) -> APIRouter:
    router = APIRouter()

    @router.post("/benchmarks/compare")
    def compare_workflows(request: BenchmarkRequest):
        """Run workflows sequentially and return chart-ready accuracy/cost/timing data.

        Sequential execution is intentional: it measures single-request latency
        without one candidate stealing another candidate's API/CPU capacity.
        """
        workflows = {}
        for workflow_id in request.workflow_ids:
            try:
                workflow = workflow_store.load(workflow_id)
            except FileNotFoundError as error:
                raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from error
            query_nodes = [node for node in workflow.graph.nodes if node.module_type == "query_input"]
            if len(query_nodes) != 1:
                raise HTTPException(status_code=422, detail=f"{workflow_id} must contain exactly one query_input node")
            workflows[workflow_id] = (workflow, query_nodes[0].id)

        rows = []
        for case in request.cases:
            for workflow_id, (workflow, query_node_id) in workflows.items():
                started = perf_counter()
                try:
                    run = workflow_executor.create_run(workflow, WorkflowExecutionRequest(
                        inputs={query_node_id: {"query": case.question}}, use_cache=request.use_cache,
                    ))
                    run = workflow_executor.execute_all(run.id)
                    metrics = _run_metrics(run)
                    metrics["latency_seconds"] = round(perf_counter() - started, 3)
                    score = _score(case, metrics["answer"])
                    error = None
                except (DagExecutionCancelled, DagExecutionError, ValueError) as exc:
                    metrics = {"run_id": None, "status": "failed", "latency_seconds": round(perf_counter() - started, 3), "total_tokens": 0, "estimated_cost_usd": 0, "answer": "", "timeline": []}
                    score = {"correct": False, "matched_numbers": 0, "expected_numbers": len(case.expected_numbers), "matched_terms": 0, "expected_terms": len(case.expected_terms)}
                    error = str(exc)
                rows.append({"workflow_id": workflow_id, "case_id": case.id, "question": case.question, **metrics, "score": score, "error": error})

        summary = []
        for workflow_id in request.workflow_ids:
            group = [row for row in rows if row["workflow_id"] == workflow_id]
            summary.append({
                "workflow_id": workflow_id,
                "cases": len(group),
                "accuracy": round(sum(row["score"]["correct"] for row in group) / len(group), 4),
                "average_latency_seconds": round(mean(row["latency_seconds"] for row in group), 3),
                "average_tokens": round(mean(row["total_tokens"] for row in group), 1),
                "average_cost_usd": round(mean(row["estimated_cost_usd"] for row in group), 6),
                "errors": sum(row["error"] is not None for row in group),
            })
        return {"execution_mode": "sequential_isolated", "use_cache": request.use_cache, "summary": summary, "results": rows}

    return router
