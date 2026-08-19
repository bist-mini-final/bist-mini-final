from pathlib import Path
import os
import sys
import tempfile
import unittest

from backend.runtime.worker import CancellableModuleWorker


class CancellableModuleWorkerTests(unittest.TestCase):
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
