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
