from backend.domains.workflow.infrastructure.postgres import WorkflowRunStateRepositoryMixin


def _row(status: str = "running") -> tuple[object, ...]:
    return (
        "run-1",
        "rag_query",
        "2026-09-01T00:00:00Z",
        status,
        2,
        {"nodes": [{"id": "query"}, {"id": "read"}], "edges": []},
        {},
        True,
        {},
        [],
        "2026-09-01T00:00:00Z",
        "2026-09-01T00:00:01Z",
    )


def test_partial_succeeded_node_set_does_not_complete_workflow_summary() -> None:
    result = WorkflowRunStateRepositoryMixin._workflow_run_summary_from_row(
        _row(),
        {"query": {"status": "succeeded"}},
    )

    assert result["status"] == "running"


def test_complete_succeeded_node_set_completes_workflow_summary() -> None:
    result = WorkflowRunStateRepositoryMixin._workflow_run_summary_from_row(
        _row(),
        {
            "query": {"status": "succeeded"},
            "read": {"status": "succeeded"},
        },
    )

    assert result["status"] == "completed"


def test_failed_node_still_fails_incomplete_workflow_summary() -> None:
    result = WorkflowRunStateRepositoryMixin._workflow_run_summary_from_row(
        _row(),
        {"query": {"status": "failed"}},
    )

    assert result["status"] == "failed"
