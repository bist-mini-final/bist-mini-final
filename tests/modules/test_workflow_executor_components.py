from __future__ import annotations

import pytest

from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.application.node_runner import WorkflowNodeRunner
from backend.domains.workflow.domain import DagExecutionError
from backend.domains.workflow.domain.models import WorkflowExecutionRequest
from backend.domains.workflow.infrastructure.job_catalog import workflow_from_job
from backend.domains.workflow.infrastructure.persistence import ResultCache, RunStore
from jobs import RAG_QUERY_JOB
from tests.modules.registry_factory import create_test_registry


def test_run_factory_rejects_unknown_runtime_node() -> None:
    executor = WorkflowExecutor(create_test_registry(), RunStore(), ResultCache())

    with pytest.raises(DagExecutionError, match="존재하지 않는 노드"):
        executor.create_run(
            workflow_from_job(RAG_QUERY_JOB),
            WorkflowExecutionRequest(inputs={"missing-node": {"query": "test"}}),
        )


def test_run_factory_applies_config_override_to_snapshot_only() -> None:
    executor = WorkflowExecutor(create_test_registry(), RunStore(), ResultCache())
    workflow = workflow_from_job(RAG_QUERY_JOB)

    run = executor.create_run(
        workflow,
        WorkflowExecutionRequest(
            config_overrides={"decompose": {"model": "test-run-model"}}
        ),
    )

    source_node = next(node for node in workflow.graph.nodes if node.id == "decompose")
    run_node = next(node for node in run.graph.nodes if node.id == "decompose")
    assert "model" not in source_node.config
    assert run_node.config["model"] == "test-run-model"


def test_node_usage_preserves_answer_and_metric_output_contracts() -> None:
    answer_cost, answer_usage = WorkflowNodeRunner._output_usage(
        {
            "answer_json": {
                "estimated_cost_usd": 0.12,
                "api_usage": {"prompt_tokens": 10, "total_tokens": 12},
            }
        },
        {},
    )
    metric_cost, metric_usage = WorkflowNodeRunner._output_usage(
        {"metrics": {"estimated_cost_usd": 0.03, "total_tokens": 7}},
        {},
    )

    assert answer_cost == 0.12
    assert answer_usage == {"prompt_tokens": 10, "total_tokens": 12}
    assert metric_cost == 0.03
    assert metric_usage == {
        "prompt_tokens": 7,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 7,
    }


def test_semantic_output_keeps_empty_usage_as_an_explicit_report() -> None:
    cost, usage = WorkflowNodeRunner._output_usage(
        {"semantic_match": {"metrics": {"estimated_cost_usd": 0.0}}},
        {},
    )

    assert cost == 0.0
    assert usage == {}
