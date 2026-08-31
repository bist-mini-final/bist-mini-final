"""Contracts for thin process entrypoints and compatibility imports."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from backend.bootstrap.application import ApplicationContainer
from backend.bootstrap.workers import registered_worker_kinds, run_worker
from backend.entrypoints.cli import COMMAND_TARGETS
from backend.platform.postgres.pool import ConnectionPoolRegistry


def test_compatibility_imports_resolve_to_canonical_types() -> None:
    assert ApplicationContainer.__module__ == "backend.bootstrap.application"
    assert ConnectionPoolRegistry.__module__ == "backend.platform.postgres.pool"


def test_management_commands_are_entrypoint_owned() -> None:
    assert COMMAND_TARGETS
    assert all(
        target.startswith("backend.entrypoints.commands.")
        for target in COMMAND_TARGETS.values()
    )


def test_worker_registry_exposes_all_deployment_kinds() -> None:
    assert set(registered_worker_kinds()) == {
        "workflow",
        "ingestion-embedding",
        "ingestion-vector",
        "bi-materialization",
        "bi-question",
        "benchmark",
    }


def test_workflow_worker_receives_queue_arguments() -> None:
    worker = Mock(return_value=0)
    runtime = Mock()
    with (
        patch("backend.bootstrap.workers._load_worker", return_value=worker),
        patch(
            "backend.bootstrap.workers.RuntimeContainer.create",
            return_value=runtime,
        ),
    ):
        assert run_worker("workflow", ("--queue", "workflow-core")) == 0
    worker.assert_called_once_with(
        ("--queue", "workflow-core"),
        services=runtime.services,
        default_queue="workflow-core",
    )
    runtime.close.assert_called_once_with()


def test_specialized_worker_rejects_undeclared_arguments() -> None:
    worker = Mock(return_value=0)
    with patch("backend.bootstrap.workers._load_worker", return_value=worker):
        with pytest.raises(ValueError, match="추가 인자"):
            run_worker("benchmark", ("--unexpected",))
    worker.assert_not_called()
