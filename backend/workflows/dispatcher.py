"""Server-owned background dispatch for persistent workflow runs."""

from __future__ import annotations

import atexit
import logging
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, TimeoutError
from threading import Lock
from typing import Collection, Dict, Optional

from .executor import DagExecutionCancelled, WorkflowExecutor
from .models import WorkflowRun, utc_now_iso
from .store import RunStore


logger = logging.getLogger(__name__)


class WorkflowRunDispatcher:
    """Execute persisted runs independently from the originating HTTP request.

    The run store remains the source of truth. The in-process queue only owns
    scheduling; interrupted queued/running runs can be submitted again after a
    server restart without creating a second run document.
    """

    def __init__(
        self,
        executor: WorkflowExecutor,
        run_store: RunStore,
        max_workers: int = 1,
    ) -> None:
        """
        Initialize a dispatcher with the workflow executor, run store, and worker capacity.
        
        Parameters:
            executor (WorkflowExecutor): Executor used to run workflows.
            run_store (RunStore): Persistent store for workflow run state.
            max_workers (int): Maximum number of background worker threads.
        """
        self.executor = executor
        self.run_store = run_store
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="workflow-run",
        )
        self._lock = Lock()
        self._futures: Dict[str, Future[object]] = {}
        atexit.register(self.shutdown)

    def submit(self, run_id: str, *, resume_failed: bool = False) -> bool:
        """
        Schedule a workflow run when it has no active execution.
        
        Parameters:
            run_id (str): Identifier of the workflow run.
            resume_failed (bool): Whether to resume failed workflow nodes.
        
        Returns:
            bool: `True` if the run was scheduled, `False` if it already has an active execution.
        """

        with self._lock:
            existing = self._futures.get(run_id)
            if existing is not None and not existing.done():
                return False
            future = self._pool.submit(
                self._execute,
                run_id,
                resume_failed,
            )
            self._futures[run_id] = future

        future.add_done_callback(
            lambda completed, active_run_id=run_id: self._forget(
                active_run_id,
                completed,
            )
        )
        return True

    def ensure_submitted(
        self,
        run_id: str,
        run: Optional[WorkflowRun] = None,
    ) -> None:
        """Resume a persisted non-terminal run when no worker currently owns it."""

        run = run or self.run_store.load(run_id)
        if run.status in ("queued", "running"):
            self.submit(run_id)

    def cancel(self, run_id: str) -> WorkflowRun:
        """
        Stop a queued or active workflow run.
        
        A queued run is marked as paused before execution begins. An active run is
        cancelled through the workflow executor, and its persisted cancellation state
        is returned.
        
        Returns:
            WorkflowRun: The persisted run state after cancellation.
        """

        with self._lock:
            future = self._futures.get(run_id)
        if future is not None and future.cancel():
            with self._lock:
                if self._futures.get(run_id) is future:
                    self._futures.pop(run_id, None)
            run = self.run_store.load(run_id)
            if run.status not in ("completed", "failed"):
                run.status = "paused"
                return self.run_store.save(run)
            return run
        run = self.executor.cancel_run(run_id)
        if future is not None:
            try:
                future.result(timeout=5)
            except (CancelledError, TimeoutError):
                pass
            except Exception:
                # The persisted paused state from cancel_run remains canonical.
                logger.exception(
                    "취소 후 백그라운드 실행 종료 확인에 실패했습니다: %s",
                    run_id,
                )
        return run

    def recover_pending(
        self,
        workflow_ids: Optional[Collection[str]] = None,
    ) -> int:
        """
        Requeue persisted workflow runs that can resume after a server restart.
        
        Parameters:
            workflow_ids (Optional[Collection[str]]): Workflow identifiers to recover. If omitted, recover eligible runs from all workflows.
        
        Returns:
            int: Number of runs successfully requeued.
        """

        allowed_workflow_ids = set(workflow_ids) if workflow_ids is not None else None
        recovered = 0
        for run in self.run_store.list():
            if allowed_workflow_ids is not None and run.workflow_id not in allowed_workflow_ids:
                continue
            if run.status not in ("queued", "running"):
                continue
            if self.submit(run.id):
                recovered += 1
        return recovered

    def is_active(self, run_id: str) -> bool:
        """Determine whether a workflow run currently has an active execution.
        
        Parameters:
        	run_id (str): Identifier of the workflow run.
        
        Returns:
        	bool: `true` if the run has an unfinished execution, `false` otherwise.
        """
        with self._lock:
            future = self._futures.get(run_id)
            return future is not None and not future.done()

    def shutdown(self, wait: bool = True) -> None:
        """Cancel tracked runs and stop the worker pool before owned paths disappear."""

        with self._lock:
            active_run_ids = [
                run_id
                for run_id, future in self._futures.items()
                if not future.done()
            ]
        for run_id in active_run_ids:
            try:
                self.cancel(run_id)
            except FileNotFoundError:
                continue
            except Exception:
                logger.exception("디스패처 종료 중 실행 취소 실패: %s", run_id)
        self._pool.shutdown(wait=wait, cancel_futures=True)

    def _execute(self, run_id: str, resume_failed: bool) -> object:
        """
        Execute or resume a workflow run in the background.
        
        Parameters:
            resume_failed (bool): Whether to resume failed work instead of starting normal execution.
        
        Returns:
            The workflow execution result, or the persisted run when execution is cancelled.
        """
        try:
            if resume_failed:
                return self.executor.resume(run_id)
            return self.executor.execute_all(run_id)
        except DagExecutionCancelled:
            logger.info("백그라운드 워크플로 실행이 사용자 요청으로 중단됐습니다: %s", run_id)
            return self.run_store.load(run_id)
        except Exception as error:
            self._persist_unexpected_failure(run_id, error)
            logger.exception("백그라운드 워크플로 실행 실패: %s", run_id)
            raise

    def _persist_unexpected_failure(self, run_id: str, error: Exception) -> None:
        """
        Persist an unexpected execution failure for a workflow run.
        
        Parameters:
            run_id (str): Identifier of the affected workflow run.
            error (Exception): Unexpected failure to record.
        """

        try:
            run = self.run_store.load(run_id)
            if run.status in ("completed", "failed"):
                return
            failed_state = next(
                (state for state in run.nodes.values() if state.status == "running"),
                None,
            ) or next(
                (state for state in run.nodes.values() if state.status == "pending"),
                None,
            )
            if failed_state is not None:
                failed_state.status = "failed"
                failed_state.outcome = "failed"
                failed_state.error = self.executor._format_error(
                    error,
                    include_type=True,
                )
                failed_state.completed_at = utc_now_iso()
                batch = run.batches[failed_state.batch_index]
                batch.status = "failed"
                batch.completed_at = utc_now_iso()
            run.status = "failed"
            self.run_store.save(run)
        except Exception:
            logger.exception(
                "백그라운드 실패 상태를 저장하지 못했습니다: %s",
                run_id,
            )

    def _forget(self, run_id: str, future: Future[object]) -> None:
        """Remove the tracked future for a run when it is still the active future."""
        with self._lock:
            if self._futures.get(run_id) is future:
                self._futures.pop(run_id, None)
