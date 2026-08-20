"""Submit persisted product runs to one Prefect deployment."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Collection, Optional, Protocol, cast
from uuid import UUID

from ...workflows.executor import WorkflowExecutor
from ...workflows.models import WorkflowRun, utc_now_iso
from ...workflows.store import RunStore

logger = logging.getLogger(__name__)


class PrefectDeploymentClient(Protocol):
    """Small boundary that keeps Prefect SDK details out of API services."""

    def submit(
        self,
        deployment_name: str,
        *,
        run_id: str,
        resume_failed: bool,
        submission_attempt: int,
    ) -> str:
        ...

    def cancel(self, external_run_id: str) -> None:
        ...


class PrefectSdkDeploymentClient:
    """Lazy Prefect SDK boundary for deployment submission and cancellation."""

    def submit(
        self,
        deployment_name: str,
        *,
        run_id: str,
        resume_failed: bool,
        submission_attempt: int,
    ) -> str:
        from prefect.deployments import run_deployment

        flow_run = run_deployment(
            name=deployment_name,
            parameters={
                "run_id": run_id,
                "resume_failed": resume_failed,
            },
            flow_run_name=f"excel-ingestion-{run_id}",
            tags=["bist", "excel-ingestion", f"product-run:{run_id}"],
            idempotency_key=f"bist:{run_id}:{submission_attempt}",
            timeout=0,
            as_subflow=False,
        )
        if inspect.isawaitable(flow_run):
            # Prefect's sync-compatible API returns a coroutine when invoked
            # while Uvicorn already owns the current thread's event loop (for
            # example during startup recovery). Bridge it through Prefect's
            # dedicated sync loop instead of calling asyncio.run in that loop.
            from prefect.utilities.asyncutils import run_coro_as_sync

            flow_run = run_coro_as_sync(
                cast(Coroutine[Any, Any, Any], flow_run)
            )
        if flow_run is None:
            raise RuntimeError("Prefect deployment 제출 결과가 없습니다")
        return str(flow_run.id)

    def cancel(self, external_run_id: str) -> None:
        from prefect.utilities.asyncutils import run_coro_as_sync

        run_coro_as_sync(self._cancel(external_run_id))

    @staticmethod
    async def _cancel(external_run_id: str) -> None:
        from prefect import get_client
        from prefect.client.schemas.objects import StateType
        from prefect.client.schemas.responses import SetStateStatus

        flow_run_id = UUID(external_run_id)
        async with get_client() as client:
            flow_run = await client.read_flow_run(flow_run_id)
            if flow_run.state is None:
                raise RuntimeError(f"Prefect flow run 상태가 없습니다: {external_run_id}")
            state = flow_run.state.model_copy(
                update={"name": "Cancelling", "type": StateType.CANCELLING}
            )
            result = await client.set_flow_run_state(flow_run_id, state, force=True)
            if result.status != SetStateStatus.ACCEPT:
                raise RuntimeError(
                    f"Prefect 취소 상태 변경이 거부되었습니다: {result.status}"
                )


@dataclass
class PrefectIngestionDispatcher:
    """Use Prefect as the sole scheduler for external ingestion runs."""

    executor: WorkflowExecutor
    run_store: RunStore
    deployment_name: str
    client: PrefectDeploymentClient

    def __init__(
        self,
        executor: WorkflowExecutor,
        run_store: RunStore,
        deployment_name: str,
        client: Optional[PrefectDeploymentClient] = None,
    ) -> None:
        self.executor = executor
        self.run_store = run_store
        self.deployment_name = deployment_name
        self.client = client or PrefectSdkDeploymentClient()

    def submit(self, run_id: str, *, resume_failed: bool = False) -> bool:
        # Submission decisions need only compact status/orchestration metadata;
        # loading a full Excel-ingestion run can deserialize hundreds of MB.
        run = self.run_store.load_summary(run_id)
        if run.status == "completed":
            return False
        if (
            run.orchestration.external_run_id is not None
            and run.status in ("queued", "running")
        ):
            return False
        if resume_failed or run.status in ("failed", "paused"):
            self.executor.prepare_resume(run_id)
        submission_attempt = run.orchestration.submission_attempt + 1
        external_run_id = self.client.submit(
            self.deployment_name,
            run_id=run_id,
            resume_failed=resume_failed,
            submission_attempt=submission_attempt,
        )
        submitted_at = utc_now_iso()
        self.run_store.update_orchestration(
            run_id,
            backend="prefect",
            deployment_name=self.deployment_name,
            external_run_id=external_run_id,
            submission_attempt=submission_attempt,
            submitted_at=submitted_at,
        )
        return True

    def ensure_submitted(
        self,
        run_id: str,
        run: Optional[WorkflowRun] = None,
    ) -> None:
        run = run or self.run_store.load(run_id)
        if (
            run.status in ("queued", "running")
            and run.orchestration.external_run_id is None
        ):
            self.submit(run_id)

    def cancel(self, run_id: str) -> WorkflowRun:
        run = self.run_store.load(run_id)
        external_run_id = run.orchestration.external_run_id
        if external_run_id is not None:
            self.client.cancel(external_run_id)
        return self.executor.cancel_run(run_id)

    def cancel_all(self) -> int:
        cancelled = 0
        for run in self.run_store.list():
            if run.status not in ("queued", "running"):
                continue
            if run.orchestration.backend != "prefect":
                continue
            self.cancel(run.id)
            cancelled += 1
        return cancelled

    def recover_pending(
        self,
        workflow_ids: Optional[Collection[str]] = None,
        max_recoveries: int = 100,
    ) -> int:
        allowed = set(workflow_ids) if workflow_ids is not None else None
        recovered = 0

        # Fast 1s health check to avoid blocking FastAPI startup when Prefect is offline
        try:
            import os
            import urllib.request
            api_url = os.getenv("PREFECT_API_URL", "http://127.0.0.1:4200/api")
            health_url = api_url.rstrip("/") + "/health"
            req = urllib.request.Request(health_url, headers={"User-Agent": "bist-mini"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status != 200:
                    return 0
        except Exception:
            logger.debug("Prefect 서버가 오프라인 상태이므로 미완료 run 복구를 건너뜁니다.")
            return 0

        database = self.run_store.db_manager
        if database is not None:
            try:
                references = database.list_pending_workflow_run_references(
                    sorted(allowed) if allowed is not None else None
                )
            except Exception as error:
                logger.warning("Prefect 복구용 run 참조 조회 실패: %s", error)
            else:
                for reference in references:
                    if recovered >= max_recoveries:
                        break
                    orchestration = reference["orchestration"]
                    if orchestration.get("external_run_id") is not None:
                        continue
                    try:
                        if self.submit(reference["run_id"]):
                            recovered += 1
                    except Exception as error:
                        logger.warning(
                            "Prefect로 미완료 run 복구 제출 실패 (run_id=%s): %s",
                            reference["run_id"],
                            error,
                        )
                return recovered

        for run in self.run_store.list_pending(allowed):
            if recovered >= max_recoveries:
                break
            if run.orchestration.external_run_id is not None:
                continue
            try:
                if self.submit(run.id):
                    recovered += 1
            except Exception as error:
                logger.warning("Prefect로 미완료 run 복구 제출 실패 (run_id=%s): %s", run.id, error)
        return recovered

    def is_active(self, run_id: str) -> bool:
        run = self.run_store.load_summary(run_id)
        return (
            run.orchestration.backend == "prefect"
            and run.orchestration.external_run_id is not None
            and run.status in ("queued", "running")
        )

    def shutdown(self) -> None:
        # Prefect owns flow-run lifecycle across API process restarts.
        return None
