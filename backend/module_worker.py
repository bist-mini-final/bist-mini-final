"""Cancellable, persistent worker process for production module execution."""

from __future__ import annotations

import atexit
from multiprocessing import get_context
from multiprocessing.process import BaseProcess
from queue import Empty
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4


class ModuleWorkerCancelled(RuntimeError):
    """Raised in the request thread after its worker process is terminated."""


class ModuleWorkerError(RuntimeError):
    """Raised when an isolated module cannot return a valid result."""


def _worker_main(request_queue, response_queue, spec: Dict[str, str]) -> None:
    """Build process-local services once and execute JSON-compatible tasks."""

    from pathlib import Path

    from .answer_cache import AnswerCacheRepository
    from .embedding_artifacts import EmbeddingArtifactStore
    from .module_registry import ModuleRegistry
    from .vector_index_store import VectorIndexStore

    registry = ModuleRegistry(
        AnswerCacheRepository(Path(spec["answer_cache_path"])),
        embedding_artifact_store=EmbeddingArtifactStore(
            Path(spec["embedding_artifact_dir"])
        ),
        vector_index_store=VectorIndexStore(Path(spec["vector_index_dir"])),
    )
    while True:
        task = request_queue.get()
        if task is None:
            return
        task_id = task["task_id"]
        try:
            output = registry.get(task["module_type"]).run(task["payload"])
            response_queue.put(
                {"task_id": task_id, "ok": True, "output": output}
            )
        except BaseException as error:  # child failures must not kill the API server
            response_queue.put(
                {
                    "task_id": task_id,
                    "ok": False,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )


class CancellableModuleWorker:
    """Own one reusable module process that can be terminated during a task."""

    def __init__(self, spec: Dict[str, str]) -> None:
        self._spec = dict(spec)
        self._context = get_context("spawn")
        self._state_lock = Lock()
        self._process: Optional[BaseProcess] = None
        self._request_queue = None
        self._response_queue = None
        self._active_task_id: Optional[str] = None
        self._active_execution_id: Optional[str] = None
        atexit.register(self.shutdown)

    def execute(
        self,
        module_type: str,
        payload: Any,
        execution_id: str,
    ) -> Any:
        task_id = uuid4().hex
        with self._state_lock:
            if self._active_task_id is not None:
                raise ModuleWorkerError("다른 모듈 작업이 이미 실행 중입니다")
            self._ensure_started_locked()
            process = self._process
            request_queue = self._request_queue
            response_queue = self._response_queue
            self._active_task_id = task_id
            self._active_execution_id = execution_id
            request_queue.put(
                {
                    "task_id": task_id,
                    "module_type": module_type,
                    "payload": payload,
                }
            )

        try:
            while True:
                try:
                    result = response_queue.get(timeout=0.05)
                except Empty:
                    with self._state_lock:
                        if self._process is not process:
                            raise ModuleWorkerCancelled("모듈 실행이 중단되었습니다")
                        if process is None or not process.is_alive():
                            exit_code = None if process is None else process.exitcode
                            self._detach_worker_locked()
                            raise ModuleWorkerError(
                                f"모듈 워커가 비정상 종료되었습니다 (exit={exit_code})"
                            )
                    continue

                if result.get("task_id") != task_id:
                    continue
                if result.get("ok") is True:
                    return result.get("output")
                error_type = result.get("error_type") or "ModuleExecutionError"
                message = result.get("error") or "격리 모듈 실행에 실패했습니다"
                raise ModuleWorkerError(f"{error_type}: {message}")
        finally:
            with self._state_lock:
                if self._active_task_id == task_id:
                    self._active_task_id = None
                    self._active_execution_id = None

    def cancel(self, execution_id: str) -> bool:
        """Terminate the process only when it is running the requested run."""

        with self._state_lock:
            if (
                self._active_task_id is None
                or self._active_execution_id != execution_id
            ):
                return False
            process = self._detach_worker_locked()
        self._terminate(process)
        return True

    def reset(self) -> bool:
        """Terminate even an idle worker so cleared domain caches cannot linger."""

        with self._state_lock:
            process = self._detach_worker_locked()
        self._terminate(process)
        return process is not None

    def shutdown(self) -> None:
        self.reset()

    def _ensure_started_locked(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        self._detach_worker_locked()
        self._request_queue = self._context.Queue()
        self._response_queue = self._context.Queue()
        self._process = self._context.Process(
            target=_worker_main,
            args=(self._request_queue, self._response_queue, self._spec),
            name="rag-module-worker",
            daemon=True,
        )
        self._process.start()

    def _detach_worker_locked(self) -> Optional[BaseProcess]:
        process = self._process
        self._process = None
        self._request_queue = None
        self._response_queue = None
        self._active_task_id = None
        self._active_execution_id = None
        return process

    @staticmethod
    def _terminate(process: Optional[BaseProcess]) -> None:
        if process is None:
            return
        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
        if process.is_alive():
            process.kill()
            process.join(timeout=1.0)

