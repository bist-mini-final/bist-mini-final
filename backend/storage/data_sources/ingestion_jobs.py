"""Application service for persistent Excel ingestion jobs.

This module deliberately has no FastAPI dependency.  HTTP routes translate
requests and errors, while the external job process executes the persisted
workflow run identified here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from backend.domains.workflow.application.dispatching import RunDispatcher
from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.domain import DagExecutionError
from backend.domains.workflow.domain.models import WorkflowExecutionRequest, WorkflowRun
from backend.domains.workflow.infrastructure.persistence import RunStore, WorkflowStore
from backend.storage.pgvector_store import PgVectorStore
from modules.common.config import DEFAULT_EMBEDDING_MODEL

INGESTION_WORKFLOW_ID = "excel_ingestion"
INGESTION_WORKFLOW_IDS = frozenset({INGESTION_WORKFLOW_ID})


class IngestionRequest(BaseModel):
    """User-selected configuration for one Excel ingestion job."""

    file_name: str = Field(
        min_length=1,
        description="data/source_files/ 내 대상 Excel 파일명",
    )
    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        description="문서 임베딩 모델 (기본값: text-embedding-3-small)",
    )
    variant_mode: Literal["header_only", "header_with_value", "both"] = Field(
        default="both",
        description="직렬화 형태 (header_only, header_with_value, both)",
    )
    structure_mode: Literal["auto", "luna_vlm"] = Field(
        default="auto",
        description=(
            "구조화 모드 (auto: Luna VLM 감지 후 직렬화, luna_vlm: 강제 VLM)"
        ),
    )
    sheet_names: Optional[List[str]] = Field(
        default=None,
        description="인덱싱할 시트 목록 (기본값: 모든 표시 시트)",
    )
    batch_size: int = Field(
        default=2048,
        ge=1,
        le=2048,
        description="임베딩 배치 크기",
    )


def _public_error(value: Optional[str], limit: int = 2000) -> Optional[str]:
    if value is None:
        return None
    message = value
    for marker in ("\n[SQL:", " [SQL:"):
        if marker in message:
            message = message.split(marker, 1)[0].rstrip()
            break
    return message if len(message) <= limit else message[:limit].rstrip() + "…"


class IngestionJobService:
    """Create, dispatch, inspect, resume, and cancel Excel ingestion runs."""

    def __init__(
        self,
        workflow_store: WorkflowStore,
        run_store: RunStore,
        workflow_executor: WorkflowExecutor,
        workflow_dispatcher: RunDispatcher,
    ) -> None:
        self.workflow_store = workflow_store
        self.run_store = run_store
        self.workflow_executor = workflow_executor
        self.workflow_dispatcher = workflow_dispatcher

    @staticmethod
    def workflow_id_for(_request: IngestionRequest) -> str:
        return INGESTION_WORKFLOW_ID

    def create_run(self, request: IngestionRequest) -> WorkflowRun:
        """Persist a queued run but do not execute work in the API process."""

        workflow = self.workflow_store.load(self.workflow_id_for(request))
        runtime_inputs: Dict[str, Dict[str, Any]] = {}
        config_overrides: Dict[str, Dict[str, Any]] = {}
        has_writer = False

        for node in workflow.graph.nodes:
            if node.module_type == "processed_file_selector":
                selector_input: Dict[str, Any] = {"file_name": request.file_name}
                if request.sheet_names is not None:
                    selector_input["sheet_names"] = request.sheet_names
                runtime_inputs[node.id] = selector_input
            elif node.module_type == "cell_text_serializer":
                config_overrides[node.id] = {
                    "variant_mode": request.variant_mode,
                }
            elif node.module_type == "cell_text_embedder":
                config_overrides[node.id] = {
                    "model": request.model,
                    "batch_size": request.batch_size,
                }
            elif node.module_type == "pgvector_index_writer":
                has_writer = True

        if not runtime_inputs:
            raise DagExecutionError(
                "인덱싱 워크플로에 processed_file_selector 모듈이 없습니다"
            )
        if not has_writer:
            raise DagExecutionError(
                "인덱싱 워크플로에 pgvector_index_writer 모듈이 없습니다"
            )

        return self.workflow_executor.create_run(
            workflow,
            WorkflowExecutionRequest(
                inputs=runtime_inputs,
                config_overrides=config_overrides,
                use_cache=True,
            ),
        )

    def create_and_submit(self, request: IngestionRequest) -> WorkflowRun:
        run = self.create_run(request)
        self.workflow_dispatcher.submit(run.id)
        # Return the queue-aware snapshot so the first HTTP response already
        # renders the durable KEDA waiting state before the worker claims it.
        return self.run_store.load_summary(run.id)

    @staticmethod
    def node_output(
        run: WorkflowRun,
        module_type: str,
    ) -> Optional[Dict[str, Any]]:
        for node in run.graph.nodes:
            if node.module_type != module_type:
                continue
            output = run.nodes[node.id].output
            if isinstance(output, dict):
                return output
        return None

    @staticmethod
    def node_state(run: WorkflowRun, module_type: str) -> Optional[Any]:
        for node in run.graph.nodes:
            if node.module_type == module_type:
                return run.nodes.get(node.id)
        return None

    def target_index_id(self, run: WorkflowRun) -> Optional[str]:
        writer_output = self.node_output(run, "pgvector_index_writer") or {}
        if isinstance(writer_output.get("index_id"), str):
            return writer_output["index_id"]
        writer_node = next(
            (
                node
                for node in run.graph.nodes
                if node.module_type == "pgvector_index_writer"
            ),
            None,
        )
        if writer_node is not None:
            target = run.nodes[writer_node.id].progress.get("target_index_id")
            if isinstance(target, str):
                return target
        embedder_output = self.node_output(run, "cell_text_embedder") or {}
        artifact_id = embedder_output.get("artifact_id")
        if isinstance(artifact_id, str):
            return PgVectorStore.index_id(artifact_id)
        return None

    def payload(
        self,
        run: WorkflowRun,
        *,
        include_index: bool = True,
    ) -> Dict[str, Any]:
        selector_output = self.node_output(run, "processed_file_selector") or {}
        structure_output = self.node_output(run, "luna_vlm_structure_detector")
        luna_output = None
        if structure_output is not None:
            luna_output = {
                **structure_output,
                "file_name": structure_output.get("file_name")
                or selector_output.get("file_name"),
                "workbook_hash": structure_output.get("workbook_hash")
                or selector_output.get("workbook_hash"),
                "sheet_names": selector_output.get("sheet_names", []),
            }

        index = None
        if include_index:
            writer_output = self.node_output(run, "pgvector_index_writer")
            embedder_output = self.node_output(run, "cell_text_embedder") or {}
            embedder_state = self.node_state(run, "cell_text_embedder")
            embedder_usage = (
                embedder_state.usage
                if embedder_state is not None and embedder_state.usage is not None
                else {}
            )
            embedder_node = next(
                (
                    node
                    for node in run.graph.nodes
                    if node.module_type == "cell_text_embedder"
                ),
                None,
            )
            company_output = self.node_output(run, "company_entity_extractor") or {}
            if writer_output is not None:
                index = {
                    **writer_output,
                    "company_name": company_output.get("display_name")
                    or company_output.get("company_name"),
                    "ticker": company_output.get("ticker"),
                    "duration_seconds": embedder_output.get("duration_seconds")
                    or (
                        embedder_state.elapsed_ms / 1000
                        if embedder_state is not None
                        and embedder_state.elapsed_ms is not None
                        else None
                    ),
                    "total_tokens": embedder_output.get("total_tokens")
                    or embedder_usage.get("total_tokens"),
                    "estimated_cost_usd": embedder_output.get("estimated_cost_usd")
                    if embedder_output.get("estimated_cost_usd") is not None
                    else (
                        embedder_state.cost_usd
                        if embedder_state is not None
                        else None
                    ),
                    "estimated_cost_krw": embedder_output.get("estimated_cost_krw"),
                    "batch_size": embedder_output.get("batch_size")
                    or (
                        embedder_node.config.get("batch_size")
                        if embedder_node is not None
                        else None
                    ),
                    "sheet_names": selector_output.get("sheet_names", []),
                    "tables": (structure_output or {}).get("tables", []),
                    "luna_output": luna_output,
                    "storage": "PostgreSQL + pgvector",
                }
        failed_state = next(
            (state for state in run.nodes.values() if state.status == "failed"),
            None,
        )
        run_summary = run.model_dump(mode="json")
        for state in run_summary["nodes"].values():
            state["input_payload"] = None
            state["output"] = None
            state["error"] = _public_error(state.get("error"))
        worker_active = (
            run.orchestration.external_run_id is not None
            and run.status == "running"
            if run.orchestration.backend == "kubernetes"
            else self.workflow_dispatcher.is_active(run.id)
        )
        return {
            "job_id": run.id,
            "status": run.status,
            "workflow_id": run.workflow_id,
            "run": run_summary,
            "index": index,
            "luna_output": luna_output,
            "target_index_id": self.target_index_id(run),
            "error": _public_error(
                failed_state.error if failed_state is not None else None
            ),
            "worker_active": worker_active,
        }

    def load(self, run_id: str) -> WorkflowRun:
        run = self.run_store.load(run_id)
        if run.workflow_id not in INGESTION_WORKFLOW_IDS:
            raise FileNotFoundError(run_id)
        return run

    def load_status(self, run_id: str) -> WorkflowRun:
        """Load the compact run projection used by frequent UI polling."""

        run = self.run_store.load_summary(run_id)
        if run.workflow_id not in INGESTION_WORKFLOW_IDS:
            raise FileNotFoundError(run_id)
        return run

    def list(self, file_name: Optional[str] = None) -> List[WorkflowRun]:
        summaries = [
            run
            for run in self.run_store.list_summaries()
            if run.workflow_id in INGESTION_WORKFLOW_IDS
        ]
        if file_name is not None:
            safe_file_name = Path(file_name).name
            runs = [
                summary
                for summary in summaries
                if any(
                    node.module_type == "processed_file_selector"
                    and Path(
                        str(
                            summary.runtime_inputs.get(node.id, {}).get(
                                "file_name",
                                "",
                            )
                        )
                    ).name
                    == safe_file_name
                    for node in summary.graph.nodes
                )
            ]
        else:
            runs = summaries
        return sorted(runs, key=lambda run: run.updated_at, reverse=True)

    def find_by_index(self, index_id: str) -> WorkflowRun:
        database = self.run_store.db_manager
        direct_lookup = getattr(database, "find_ingestion_run_id_by_index", None)
        if callable(direct_lookup):
            run_id = direct_lookup(index_id)
            if isinstance(run_id, str):
                return self.load_status(run_id)

        # Optional in-memory operation is retained for isolated module tests.
        for summary in self.list():
            writer_output = self.node_output(summary, "pgvector_index_writer")
            if writer_output and writer_output.get("index_id") == index_id:
                return summary
        raise FileNotFoundError(index_id)

    def resume(self, run_id: str) -> WorkflowRun:
        run = self.load(run_id)
        if run.status == "completed":
            raise ValueError("완료된 인덱싱 작업은 재개할 수 없습니다")
        if run.status == "failed":
            self.workflow_dispatcher.submit(run_id, resume_failed=True)
        elif run.status in ("queued", "running", "paused"):
            self.workflow_dispatcher.submit(run_id)
        return self.run_store.load(run_id)

    def cancel(self, run_id: str) -> WorkflowRun:
        self.load(run_id)
        self.workflow_dispatcher.cancel(run_id)
        return self.load(run_id)
