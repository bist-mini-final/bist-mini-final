from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.workflows.store import _atomic_write_text


def test_atomic_write_retries_transient_windows_permission_error() -> None:
    original_replace = Path.replace

    with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
        target = Path(temporary_directory) / "retry.json"
        attempts = 0

        def flaky_replace(source: Path, destination: Path) -> Path:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError(5, "Access is denied")
            return original_replace(source, destination)

        with patch.object(Path, "replace", autospec=True, side_effect=flaky_replace):
            _atomic_write_text(target, '{"status":"ok"}\n')

        assert target.read_text(encoding="utf-8") == '{"status":"ok"}\n'
        assert attempts == 2
        assert list(target.parent.glob("retry.json.*.tmp")) == []


def test_atomic_write_propagates_permission_error_after_all_retries() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
        target = Path(temporary_directory) / "retry.json"
        attempts = 0

        def always_fails_replace(source: Path, destination: Path) -> Path:
            nonlocal attempts
            attempts += 1
            raise PermissionError(5, "Access is denied")

        with patch.object(Path, "replace", autospec=True, side_effect=always_fails_replace):
            with patch("backend.workflows.store.time.sleep"):
                try:
                    _atomic_write_text(target, '{"status":"ok"}\n')
                    assert False, "Expected PermissionError to propagate"
                except PermissionError:
                    pass  # Expected

        assert attempts == 6
        assert list(target.parent.glob("retry.json.*.tmp")) == []


def test_run_store_file_only() -> None:
    from backend.workflows.models import WorkflowGraph, WorkflowRun
    from backend.workflows.store import RunStore

    with TemporaryDirectory() as temp_dir:
        store = RunStore(Path(temp_dir))
        run = WorkflowRun(
            id="run-file-1",
            workflow_id="test_wf",
            workflow_updated_at="2026-08-20T00:00:00+00:00",
            status="queued",
            graph=WorkflowGraph(nodes=[], edges=[]),
            batches=[],
            nodes={},
        )
        store.save(run)
        loaded = store.load("run-file-1")
        assert loaded.id == "run-file-1"
        assert len(store.list()) == 1
        assert store.delete("run-file-1") is True
        assert len(store.list()) == 0


def test_run_store_with_db_manager() -> None:
    from unittest.mock import MagicMock
    from backend.workflows.models import WorkflowGraph, WorkflowRun
    from backend.workflows.store import RunStore

    mock_db = MagicMock()
    mock_db.is_connected.return_value = True

    with TemporaryDirectory() as temp_dir:
        store = RunStore(Path(temp_dir), db_manager=mock_db)
        run = WorkflowRun(
            id="run-db-1",
            workflow_id="test_wf",
            workflow_updated_at="2026-08-20T00:00:00+00:00",
            status="running",
            graph=WorkflowGraph(nodes=[], edges=[]),
            batches=[],
            nodes={},
        )

        mock_db.get_workflow_run.return_value = run.model_dump(mode="json")
        mock_db.list_workflow_runs.return_value = [run.model_dump(mode="json")]
        mock_db.delete_workflow_run.return_value = True

        store.save(run)
        mock_db.save_workflow_run.assert_called_once()

        loaded = store.load("run-db-1")
        assert loaded.id == "run-db-1"
        mock_db.get_workflow_run.assert_called_with("run-db-1")

        runs = store.list()
        assert len(runs) == 1
        mock_db.list_workflow_runs.assert_called_with(None)

        assert store.delete("run-db-1") is True
        mock_db.delete_workflow_run.assert_called_with("run-db-1")


def test_list_summaries_merges_database_and_local_history() -> None:
    from unittest.mock import MagicMock

    from backend.workflows.models import WorkflowGraph, WorkflowRun
    from backend.workflows.store import RunStore

    mock_db = MagicMock()
    mock_db.is_connected.return_value = True
    database_run = WorkflowRun(
        id="run-db-only",
        workflow_id="indexing_pgvector_exhaustive",
        workflow_updated_at="2026-08-20T00:00:00+00:00",
        status="completed",
        graph=WorkflowGraph(nodes=[], edges=[]),
        batches=[],
        nodes={},
    )
    mock_db.list_workflow_run_summaries.return_value = [
        database_run.model_dump(mode="json")
    ]

    with TemporaryDirectory() as temp_dir:
        store = RunStore(Path(temp_dir), db_manager=mock_db)
        local_run = WorkflowRun(
            id="run-local-only",
            workflow_id="indexing_pgvector_exhaustive",
            workflow_updated_at="2026-08-20T00:00:00+00:00",
            status="completed",
            graph=WorkflowGraph(nodes=[], edges=[]),
            batches=[],
            nodes={},
        )
        store._write_summary(local_run)

        runs = store.list_summaries("indexing_pgvector_exhaustive")

        assert {run.id for run in runs} == {"run-db-only", "run-local-only"}
        mock_db.list_workflow_run_summaries.assert_called_once_with(
            "indexing_pgvector_exhaustive"
        )
