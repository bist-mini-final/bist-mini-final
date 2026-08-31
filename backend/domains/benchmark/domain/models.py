"""Benchmark request, evaluation, and claimed-work item models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


@dataclass(frozen=True)
class PlanSignature:
    metrics: tuple[str, ...] = ()
    periods: tuple[int, ...] = ()


class ExpectedPlan(BaseModel):
    metrics: list[str] = Field(default_factory=list)
    periods: list[int] = Field(default_factory=list)


class BenchmarkCase(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_numbers: list[float] = Field(default_factory=list)
    expected_terms: list[str] = Field(default_factory=list)
    expected_target: str | None = None
    expected_sheets: list[str] | None = None
    expected_abstain: bool = False
    expected_plan: ExpectedPlan | None = None


class BenchmarkRequest(BaseModel):
    workflow_ids: list[str] = Field(min_length=2, max_length=12)
    cases: list[BenchmarkCase] = Field(min_length=1, max_length=200)
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


@dataclass(frozen=True, slots=True)
class ClaimedBenchmarkJob:
    job_id: str
    request_payload: dict[str, Any]
    result_rows: tuple[dict[str, Any], ...]
    active_run_id: str | None
    current_payload: dict[str, Any] | None
    worker_id: str


__all__ = [
    "BenchmarkCase",
    "BenchmarkRequest",
    "ClaimedBenchmarkJob",
    "ExpectedPlan",
    "PlanSignature",
]
