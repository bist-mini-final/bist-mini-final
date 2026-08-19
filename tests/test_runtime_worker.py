import os
import sys
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import patch

from backend.runtime.worker import CancellableModuleWorker, ModuleWorkerError


class _FakeProcess:
    exitcode = None

    def __init__(self) -> None:
        self.alive = True
        self.terminated = False

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.alive = False
        self.terminated = True

    def join(self, timeout: float) -> None:
        pass

    def kill(self) -> None:
        self.alive = False


class CancellableModuleWorkerTests(unittest.TestCase):
    def _worker_with_responses(self, *responses):
        worker = CancellableModuleWorker({})
        process = _FakeProcess()
        worker._process = process
        worker._request_queue = Queue()
        worker._response_queue = Queue()
        for response in responses:
            worker._response_queue.put({"task_id": "task-id", **response})
        return worker, process

    @patch("backend.runtime.worker.uuid4")
    def test_progress_callback_failure_terminates_worker(self, mock_uuid4) -> None:
        mock_uuid4.return_value.hex = "task-id"
        worker, process = self._worker_with_responses(
            {"event": "progress", "progress": {"completed_items": 1}},
        )

        def fail_progress(_progress) -> None:
            raise RuntimeError("save failed")

        with self.assertRaisesRegex(
            ModuleWorkerError,
            "진행률 콜백 처리에 실패했습니다",
        ) as raised:
            worker.execute("module", {}, {}, "run-id", fail_progress)

        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertTrue(process.terminated)
        self.assertIsNone(worker._process)
        self.assertIsNone(worker._active_task_id)

    @patch("backend.runtime.worker.uuid4")
    def test_successful_progress_callback_keeps_worker_reusable(self, mock_uuid4) -> None:
        mock_uuid4.return_value.hex = "task-id"
        worker, process = self._worker_with_responses(
            {"event": "progress", "progress": {"completed_items": 1}},
            {"ok": True, "output": {"done": True}},
        )
        progress = []
        try:
            output = worker.execute("module", {}, {}, "run-id", progress.append)

            self.assertEqual(output, {"done": True})
            self.assertEqual(progress, [{"completed_items": 1}])
            self.assertIs(worker._process, process)
            self.assertFalse(process.terminated)
        finally:
            worker.shutdown()

    def test_worker_start_redirects_broken_standard_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = CancellableModuleWorker(
                {
                    "answer_cache_path": str(root / "answers.json"),
                    "embedding_artifact_dir": str(root / "embeddings"),
                    "vector_index_dir": str(root / "indexes"),
                    "processed_dir": str(root / "processed"),
                    "spreadsheet_artifact_dir": str(root / "spreadsheets"),
                }
            )
            original_stdout = sys.stdout
            read_fd, write_fd = os.pipe()
            os.close(read_fd)
            broken_stdout = os.fdopen(write_fd, "w")
            broken_stdout.write("buffered output")
            sys.stdout = broken_stdout
            try:
                worker._ensure_started_locked()
                broken_stdout.write("safe output")
                broken_stdout.flush()
            finally:
                sys.stdout = original_stdout
                worker.shutdown()
                broken_stdout.close()


if __name__ == "__main__":
    unittest.main()
