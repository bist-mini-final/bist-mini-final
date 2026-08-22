from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging
from typing import Final, assert_never
from unicodedata import normalize

from pydantic import ValidationError

from backend.modules.index_company_persistence import (
    IndexCompanyPersistenceOutputDTO,
)
from backend.modules.vector_index_writer import VectorIndexDTO
from backend.workflows.dispatcher import InteractiveWorkflowDispatcher
from backend.workflows.executor import WorkflowExecutor
from backend.workflows.models import RunNodeState, WorkflowRun
from backend.workflows.store import RunStore

from .api_services import BiApiServices
from .models import (
    BiMaterializationRequest,
    BiMaterializationSource,
    CompanyId,
)
from .materialization_scheduler import (
    BiMaterializationScheduler,
    BiScheduleResult,
    ThreadedBiMaterializationSubmitter,
)
from .snapshot_store import BiSnapshotStoreCorruption


logger = logging.getLogger(__name__)

INGESTION_WORKFLOW_IDS: Final = frozenset(
    {"indexing_pgvector", "indexing_pgvector_exhaustive"}
)


@dataclass(frozen=True, slots=True)
class BiIndexingCompletionContractError(Exception):
    run_id: str
    code: str

    def __str__(self) -> str:
        return f"{self.run_id}: {self.code}"


class BiIndexingCompletionAdapter:
    def to_request(self, run: WorkflowRun) -> BiMaterializationRequest | None:
        if run.workflow_id not in INGESTION_WORKFLOW_IDS:
            return None
        match run.status:
            case "completed":
                pass
            case "queued" | "running" | "paused" | "failed":
                return None
            case unreachable:
                assert_never(unreachable)

        writer_state = self._node_state(run, "pgvector_index_writer")
        company_state = self._node_state(run, "index_company_persistence")
        if writer_state is None:
            raise BiIndexingCompletionContractError(run.id, "index_output_missing")
        if company_state is None:
            raise BiIndexingCompletionContractError(run.id, "company_output_missing")

        try:
            index = VectorIndexDTO.model_validate(writer_state.output)
            company = IndexCompanyPersistenceOutputDTO.model_validate(
                company_state.output
            )
            if company.index_id != index.index_id:
                raise BiIndexingCompletionContractError(
                    run.id,
                    "index_company_lineage_mismatch",
                )
            identity = company.ticker or company.company_name
            normalized_identity = " ".join(
                normalize("NFKC", identity).casefold().split()
            )
            company_id = CompanyId(
                "company-"
                + sha256(normalized_identity.encode("utf-8")).hexdigest()[:24]
            )
            return BiMaterializationRequest(
                company_id=company_id,
                display_name=company.company_name,
                source=BiMaterializationSource(
                    file_name=index.file_name,
                    workbook_hash=index.workbook_hash,
                    index_id=index.index_id,
                ),
            )
        except ValidationError as error:
            raise BiIndexingCompletionContractError(
                run.id,
                "invalid_indexing_output",
            ) from error

    @staticmethod
    def _node_state(run: WorkflowRun, module_type: str) -> RunNodeState | None:
        for node in run.graph.nodes:
            if node.module_type == module_type:
                return run.nodes.get(node.id)
        return None


class BiIngestionCompletionHook:
    def __init__(
        self,
        adapter: BiIndexingCompletionAdapter,
        scheduler: BiMaterializationScheduler,
    ) -> None:
        self._adapter = adapter
        self._scheduler = scheduler

    def handle(self, run: WorkflowRun) -> BiScheduleResult | None:
        request = self._adapter.to_request(run)
        if request is None:
            return None
        return self._scheduler.schedule(request)

    def shutdown(self, wait: bool = True) -> None:
        self._scheduler.shutdown(wait)


class BiWorkflowRunDispatcher(InteractiveWorkflowDispatcher):
    def __init__(
        self,
        executor: WorkflowExecutor,
        run_store: RunStore,
        completion_hook: BiIngestionCompletionHook,
        max_workers: int = 1,
    ) -> None:
        self._completion_hook = completion_hook
        super().__init__(executor, run_store, max_workers=max_workers)

    def _execute(self, run_id: str, resume_failed: bool) -> WorkflowRun:
        super()._execute(run_id, resume_failed)
        run = self.run_store.load(run_id)
        try:
            self._completion_hook.handle(run)
        except BiIndexingCompletionContractError as error:
            logger.warning(
                "BI 자동 등록 입력이 유효하지 않습니다: run_id=%s code=%s",
                error.run_id,
                error.code,
            )
        except (BiSnapshotStoreCorruption, OSError, RuntimeError) as error:
            logger.warning(
                "BI 자동 등록을 완료하지 못했습니다: run_id=%s error_type=%s",
                run_id,
                type(error).__name__,
            )
        return run

    def shutdown(self, wait: bool = True) -> None:
        super().shutdown(wait)
        self._completion_hook.shutdown(wait)


def create_bi_workflow_dispatcher(
    executor: WorkflowExecutor,
    run_store: RunStore,
    services: BiApiServices,
    max_workers: int = 1,
) -> BiWorkflowRunDispatcher:
    submitter = ThreadedBiMaterializationSubmitter(services.runner)
    scheduler = BiMaterializationScheduler(services, submitter)
    return BiWorkflowRunDispatcher(
        executor,
        run_store,
        BiIngestionCompletionHook(BiIndexingCompletionAdapter(), scheduler),
        max_workers=max_workers,
    )
