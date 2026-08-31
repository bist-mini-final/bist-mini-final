from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import Lock
from typing import Any, Collection, Dict, Generic, Iterator, List, Optional, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from backend.domains.workflow.application.history import compact_history_value
from backend.domains.workflow.domain.models import (
    IDENTIFIER_PATTERN,
    RunNodeState,
    WorkflowDocument,
    WorkflowRun,
    WorkflowSaveRequest,
    utc_now_iso,
)

ModelType = TypeVar("ModelType", bound=BaseModel)
_EXTERNAL_RUN_ID_UNSET = object()
_ARTIFACT_KEY = "_workflow_artifact"
_ARTIFACT_THRESHOLD_BYTES = 128 * 1024


def _atomic_write_text(path: Path, content: str) -> None:
    """
    Atomically write text to a file, retrying replacement after transient permission errors.

    Parameters:
        path (Path): Destination file path.
        content (str): Text to write.
    """

    temporary_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temporary_path.write_text(content, encoding="utf-8")
    try:
        for attempt in range(6):
            try:
                temporary_path.replace(path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_identifier(value: str) -> str:
    """
    Validate an identifier against the permitted identifier pattern.

    Parameters:
        value (str): Identifier to validate.

    Returns:
        str: The unchanged identifier when it is valid.

    Raises:
        ValueError: If the identifier does not match the permitted pattern.
    """
    import re

    if not re.fullmatch(IDENTIFIER_PATTERN, value):
        raise ValueError(f"유효하지 않은 식별자입니다: {value}")
    return value


class JsonModelStore(Generic[ModelType]):
    """Small atomic JSON store used by editable definitions and run state."""

    def __init__(self, directory: Path, model_type: Type[ModelType]) -> None:
        self.directory = directory
        self.model_type = model_type
        self._lock = Lock()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, document_id: str) -> Path:
        return self.directory / f"{_validate_identifier(document_id)}.json"

    def load(self, document_id: str) -> ModelType:
        path = self._path(document_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        return self.model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def write(self, document_id: str, document: ModelType) -> ModelType:
        """Persist a model document under the specified identifier and return it."""
        path = self._path(document_id)
        serialized = document.model_dump_json(indent=2)
        with self._lock:
            _atomic_write_text(path, serialized + "\n")
        return document

    @staticmethod
    def _replace_with_retry(temporary_path: Path, path: Path) -> None:
        """Retry a short-lived Windows file lock held by a run-list reader."""

        last_error: PermissionError | None = None
        for _ in range(8):
            try:
                temporary_path.replace(path)
                return
            except PermissionError as error:
                last_error = error
                time.sleep(0.05)
        if last_error is not None:
            raise last_error

    def list_documents(self) -> List[ModelType]:
        """
        Load all JSON documents from the store in filename order.

        Returns:
            List[ModelType]: The validated documents found in the store.
        """
        return [
                self.model_type.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.directory.glob("*.json"))
        ]

    def delete(self, document_id: str) -> bool:
        """
        Delete the stored document with the specified identifier.

        Parameters:
            document_id (str): Identifier of the document to delete.

        Returns:
            bool: `True` if the document was deleted, `False` if it did not exist.
        """
        path = self._path(document_id)
        with self._lock:
            if not path.is_file():
                return False
            path.unlink()
            return True

    def clear(self) -> int:
        """
        Remove all JSON files from the store.

        Returns:
            int: The number of files removed.
        """
        removed = 0
        with self._lock:
            for path in self.directory.glob("*.json"):
                path.unlink()
                removed += 1
        return removed


class WorkflowStore:
    def __init__(self, directory: Path) -> None:
        self._store = JsonModelStore(directory, WorkflowDocument)

    def save(
        self, workflow_id: str, request: WorkflowSaveRequest
    ) -> WorkflowDocument:
        from backend.domains.workflow.infrastructure.job_catalog import canonical_workflow

        if canonical_workflow(workflow_id) is not None:
            raise ValueError(
                f"canonical workflow는 jobs 정의에서만 변경할 수 있습니다: {workflow_id}"
            )
        document = WorkflowDocument(
            id=_validate_identifier(workflow_id),
            name=request.name,
            updated_at=utc_now_iso(),
            graph=request.graph,
            kind="user",
            editable=True,
            template=False,
        )
        return self._store.write(workflow_id, document)

    def load(self, workflow_id: str) -> WorkflowDocument:
        from backend.domains.workflow.infrastructure.job_catalog import canonical_workflow

        canonical = canonical_workflow(workflow_id)
        if canonical is not None:
            return canonical
        return self._store.load(workflow_id).model_copy(
            update={"kind": "user", "editable": True, "template": False}
        )

    def list(self) -> List[WorkflowDocument]:
        from backend.domains.workflow.infrastructure.job_catalog import canonical_workflows

        documents: List[WorkflowDocument] = list(canonical_workflows())
        canonical_ids = {document.id for document in documents}
        for path in sorted(self._store.directory.glob("*.json")):
            doc = WorkflowDocument.model_validate_json(path.read_text(encoding="utf-8"))
            # Always use the filename stem as the id so the UI shows actual filenames
            if doc.id != path.stem:
                doc = doc.model_copy(update={"id": path.stem})
            if doc.id in canonical_ids:
                continue
            documents.append(
                doc.model_copy(
                    update={"kind": "user", "editable": True, "template": False}
                )
            )
        return documents

    def delete(self, workflow_id: str) -> None:
        from backend.domains.workflow.infrastructure.job_catalog import canonical_workflow

        if canonical_workflow(workflow_id) is not None:
            raise ValueError("canonical/current workflow는 삭제할 수 없습니다")
        self._store.delete(workflow_id)


logger = logging.getLogger(__name__)


class RunStore:
    """PostgreSQL source of truth with optional in-memory test operation."""

    def __init__(
        self,
        directory: Optional[Path] = None,
        db_manager: Optional[Any] = None,
        *,
        require_database: bool = False,
    ) -> None:
        self.directory = directory
        self._artifact_directory = (
            directory / "artifacts" if directory is not None else None
        )
        if self._artifact_directory is not None:
            self._artifact_directory.mkdir(parents=True, exist_ok=True)
        self._memory_runs: Dict[str, WorkflowRun] = {}
        self._memory_lock = Lock()
        self._lease_context: ContextVar[Optional[tuple[str, str]]] = ContextVar(
            f"workflow_lease_{id(self)}",
            default=None,
        )
        self.db_manager = (
            db_manager
            if db_manager is not None
            and getattr(db_manager, "is_connected", lambda: False)()
            else None
        )
        self.require_database = require_database
        if self.require_database and self.db_manager is None:
            raise RuntimeError(
                "WorkflowRun 영속화에는 PostgreSQL 연결이 필요합니다"
            )

    @property
    def supports_durable_queue(self) -> bool:
        """Return whether this store can enqueue durable Kubernetes work."""

        return self.db_manager is not None

    def _externalize_output(self, run_id: str, node_id: str, value: Any) -> Any:
        """Store large JSON output once on the shared volume and return a DB ref."""

        if value is None or self._artifact_directory is None:
            return value
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(serialized) < _ARTIFACT_THRESHOLD_BYTES:
            return value
        digest = hashlib.sha256(serialized).hexdigest()
        path = self._artifact_directory / f"{run_id}.{node_id}.{digest}.json.gz"
        if not path.is_file():
            temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
            try:
                with gzip.open(temporary, "wb", compresslevel=3) as target:
                    target.write(serialized)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return {
            _ARTIFACT_KEY: {
                "file": path.name,
                "sha256": digest,
                "bytes": len(serialized),
            }
        }

    def _hydrate_output(self, value: Any) -> Any:
        if not isinstance(value, dict) or set(value) != {_ARTIFACT_KEY}:
            return value
        metadata = value.get(_ARTIFACT_KEY)
        if not isinstance(metadata, dict) or self._artifact_directory is None:
            return value
        file_name = metadata.get("file")
        digest = metadata.get("sha256")
        if not isinstance(file_name, str) or not isinstance(digest, str):
            return value
        path = self._artifact_directory / Path(file_name).name
        with gzip.open(path, "rb") as source:
            serialized = source.read()
        if hashlib.sha256(serialized).hexdigest() != digest:
            raise ValueError(f"워크플로 output artifact 해시가 일치하지 않습니다: {path.name}")
        return json.loads(serialized)

    def _database_copy(
        self,
        run: WorkflowRun,
        node_ids: Optional[Collection[str]] = None,
    ) -> WorkflowRun:
        selected = set(node_ids) if node_ids is not None else set(run.nodes)
        nodes = {
            node_id: state.model_copy(
                deep=False,
                update={
                    "output": self._externalize_output(run.id, node_id, state.output)
                },
            )
            if node_id in selected
            else state
            for node_id, state in run.nodes.items()
        }
        return run.model_copy(deep=False, update={"nodes": nodes})

    def _hydrate_run(self, run: WorkflowRun) -> WorkflowRun:
        hydrated = {
            node_id: state.model_copy(
                deep=False,
                update={"output": self._hydrate_output(state.output)},
            )
            for node_id, state in run.nodes.items()
        }
        return run.model_copy(deep=False, update={"nodes": hydrated})

    @contextmanager
    def workflow_lease(self, run_id: str, lease_token: str) -> Iterator[None]:
        """Bind one DB lease generation to persistence in this execution context."""
        context_token = self._lease_context.set((run_id, lease_token))
        try:
            yield
        finally:
            self._lease_context.reset(context_token)

    def _lease_token_for(self, run_id: str) -> Optional[str]:
        active = self._lease_context.get()
        return active[1] if active is not None and active[0] == run_id else None

    def _summary(self, run: WorkflowRun) -> WorkflowRun:
        """Create a compact run copy without deep-copying large node outputs."""
        return run.model_copy(
            deep=False,
            update={
                "runtime_inputs": compact_history_value(run.runtime_inputs),
                "nodes": {
                    node_id: state.model_copy(
                        deep=False,
                        update={
                            "input_payload": compact_history_value(
                                state.input_payload
                            ),
                            "output": compact_history_value(state.output),
                        },
                    )
                    for node_id, state in run.nodes.items()
                },
            },
        )

    def save(self, run: WorkflowRun) -> WorkflowRun:
        """Persist to PostgreSQL before publishing the process-local copy."""
        run.updated_at = utc_now_iso()
        lease_token = self._lease_token_for(run.id)
        if self.db_manager is not None:
            try:
                self.db_manager.save_workflow_run(
                    self._database_copy(run),
                    lease_token=lease_token,
                )
            except Exception as error:
                logger.warning("DB에 WorkflowRun 저장 실패 (run_id=%s): %s", run.id, error)
                raise RuntimeError(
                    "WorkflowRun을 PostgreSQL에 저장할 수 없습니다"
                ) from error
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 영속화에는 PostgreSQL 연결이 필요합니다"
            )
        with self._memory_lock:
            self._memory_runs[run.id] = run
        return run

    def save_progress(self, run: WorkflowRun, node_id: str) -> WorkflowRun:
        """Persist live progress durably before updating the local projection."""
        run.updated_at = utc_now_iso()
        lease_token = self._lease_token_for(run.id)
        if self.db_manager is not None:
            try:
                self.db_manager.save_workflow_node_progress(
                    run,
                    node_id,
                    lease_token=lease_token,
                )
            except Exception as error:
                logger.warning(
                    "DB에 WorkflowRun 진행률 저장 실패 (run_id=%s, node_id=%s): %s",
                    run.id,
                    node_id,
                    error,
                )
                raise RuntimeError(
                    "WorkflowRun 진행률을 PostgreSQL에 저장할 수 없습니다"
                ) from error
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 진행률 영속화에는 PostgreSQL 연결이 필요합니다"
            )
        with self._memory_lock:
            self._memory_runs[run.id] = run
        return run

    def save_node(self, run: WorkflowRun, node_id: str) -> WorkflowRun:
        """Persist one terminal node transition without rewriting the full run."""

        run.updated_at = utc_now_iso()
        if self.db_manager is not None:
            try:
                database_run = self._database_copy(run, (node_id,))
                self.db_manager.save_workflow_node_state(
                    database_run,
                    node_id,
                    lease_token=self._lease_token_for(run.id),
                )
            except Exception as error:
                logger.warning(
                    "DB에 WorkflowRun 노드 저장 실패 (run_id=%s, node_id=%s): %s",
                    run.id,
                    node_id,
                    error,
                )
                raise
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 노드 영속화에는 PostgreSQL 연결이 필요합니다"
            )
        with self._memory_lock:
            self._memory_runs[run.id] = run
        return run

    def enqueue(
        self,
        run_id: str,
        queue_name: str,
        *,
        submission_attempt: int,
        submitted_at: str,
        priority: int = 0,
    ) -> bool:
        """Persist queue metadata in memory and DB."""
        if self.db_manager is None:
            raise RuntimeError(
                "Kubernetes 배치 큐에는 PostgreSQL 연결이 필요합니다"
            )
        try:
            enqueued = self.db_manager.enqueue_workflow_run(
                run_id,
                queue_name,
                submission_attempt=submission_attempt,
                submitted_at=submitted_at,
                priority=priority,
            )
        except Exception as error:
            raise RuntimeError(
                "WorkflowRun을 Kubernetes PostgreSQL 큐에 넣을 수 없습니다"
            ) from error
        if enqueued is False:
            return False
        with self._memory_lock:
            if run_id in self._memory_runs:
                run = self._memory_runs[run_id]
                run.status = "queued"
                run.orchestration.backend = "kubernetes"
                run.orchestration.deployment_name = queue_name
                run.orchestration.submission_attempt = submission_attempt
                run.orchestration.submitted_at = submitted_at
                run.updated_at = utc_now_iso()
        return True

    def request_cancel(self, run_id: str) -> bool:
        """Persist cancellation in memory and DB."""
        if self.db_manager is not None:
            try:
                persisted = bool(self.db_manager.request_workflow_cancel(run_id))
            except Exception as error:
                raise RuntimeError(
                    "WorkflowRun 취소 요청을 PostgreSQL에 저장할 수 없습니다"
                ) from error
            if not persisted:
                return False
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 취소 요청에는 PostgreSQL 연결이 필요합니다"
            )
        with self._memory_lock:
            if run_id in self._memory_runs:
                self._memory_runs[run_id].status = "paused"
                self._memory_runs[run_id].updated_at = utc_now_iso()
        return True

    def is_cancel_requested(self, run_id: str) -> bool:
        """Check the cross-process cancellation flag."""
        with self._memory_lock:
            if run_id in self._memory_runs and self._memory_runs[run_id].status == "paused":
                return True
        if self.db_manager is None:
            return False
        return bool(self.db_manager.is_workflow_cancel_requested(run_id))

    def clear_cancel_request(self, run_id: str) -> None:
        """Clear durable and process-local cancellation before an explicit resume."""

        if self.db_manager is not None:
            try:
                self.db_manager.clear_workflow_cancel_request(run_id)
            except Exception as error:
                raise RuntimeError(
                    "WorkflowRun 취소 상태를 PostgreSQL에서 초기화할 수 없습니다"
                ) from error
        with self._memory_lock:
            run = self._memory_runs.get(run_id)
            if run is not None and run.status == "paused":
                run.status = "queued"

    def load(self, run_id: str) -> WorkflowRun:
        """Load a complete workflow run by its identifier."""
        # A worker holding the lease owns the freshest in-process graph. API
        # processes do not: always refresh their cross-process view from DB.
        if self._lease_token_for(run_id) is not None:
            with self._memory_lock:
                if run_id in self._memory_runs:
                    return self._memory_runs[run_id]

        if self.db_manager is not None:
            try:
                data = self.db_manager.get_workflow_run(run_id)
                if data is not None:
                    run = self._hydrate_run(WorkflowRun.model_validate(data))
                    with self._memory_lock:
                        self._memory_runs[run_id] = run
                    return run
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 로드 실패 (run_id=%s): %s", run_id, error)
                if self.require_database:
                    raise RuntimeError(
                        "WorkflowRun을 PostgreSQL에서 조회할 수 없습니다"
                    ) from error

            if self.require_database:
                raise FileNotFoundError(f"실행 {run_id}를 찾을 수 없습니다")
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 조회에는 PostgreSQL 연결이 필요합니다"
            )

        with self._memory_lock:
            if run_id in self._memory_runs:
                return self._memory_runs[run_id]

        raise FileNotFoundError(f"실행 {run_id}를 찾을 수 없습니다")

    def load_node(self, run_id: str, node_id: str) -> RunNodeState:
        """Load one node's current full input/config/output DTO snapshot."""

        if self.db_manager is not None:
            try:
                data = self.db_manager.get_workflow_node_execution_log(run_id, node_id)
                if data is not None:
                    state = RunNodeState.model_validate(
                        {
                            key: data.get(key)
                            for key in RunNodeState.model_fields
                            if key in data
                        }
                        | {
                            "cache_key": None,
                            "skip_reason": None,
                        }
                    )
                    return state.model_copy(
                        deep=False,
                        update={"output": self._hydrate_output(state.output)},
                    )
            except Exception as error:
                logger.warning(
                    "DB에서 노드 실행 상세 로드 실패 (run_id=%s node_id=%s): %s",
                    run_id,
                    node_id,
                    error,
                )
                if self.require_database:
                    raise RuntimeError(
                        "노드 실행 상세를 PostgreSQL에서 조회할 수 없습니다"
                    ) from error
            if self.require_database:
                raise FileNotFoundError(
                    f"실행 {run_id}에서 노드 {node_id}를 찾을 수 없습니다"
                )

        run = self.load(run_id)
        try:
            return run.nodes[node_id]
        except KeyError as error:
            raise FileNotFoundError(
                f"실행 {run_id}에서 노드 {node_id}를 찾을 수 없습니다"
            ) from error

    def load_summary(self, run_id: str) -> WorkflowRun:
        """Load a compact run snapshot."""
        if self.db_manager is not None:
            try:
                data = self.db_manager.get_workflow_run_summary(run_id)
                if data is not None:
                    run = WorkflowRun.model_validate(data)
                    with self._memory_lock:
                        local = self._memory_runs.get(run_id)
                        if local is None or run.updated_at >= local.updated_at:
                            self._memory_runs[run_id] = run
                    return run
            except Exception as error:
                logger.warning(
                    "DB에서 WorkflowRun 요약 로드 실패 (run_id=%s): %s",
                    run_id,
                    error,
                )
                if self.require_database:
                    raise RuntimeError(
                        "WorkflowRun 요약을 PostgreSQL에서 조회할 수 없습니다"
                    ) from error
            if self.require_database:
                raise FileNotFoundError(f"실행 {run_id}를 찾을 수 없습니다")
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 요약 조회에는 PostgreSQL 연결이 필요합니다"
            )
        return self._summary(self.load(run_id))

    def list_summaries(
        self,
        workflow_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[WorkflowRun]:
        """List compact run snapshots from memory and DB."""
        with self._memory_lock:
            local_runs = [
                self._summary(run)
                for run in self._memory_runs.values()
                if workflow_id is None or run.workflow_id == workflow_id
            ]

        if self.db_manager is not None:
            try:
                records = self.db_manager.list_workflow_run_summaries(
                    workflow_id,
                    limit=limit,
                )
                database_runs = [
                    WorkflowRun.model_validate(record) for record in records
                ]
                merged = {run.id: run for run in local_runs}
                for run in database_runs:
                    existing = merged.get(run.id)
                    if existing is None or run.updated_at >= existing.updated_at:
                        merged[run.id] = run
                ordered = sorted(
                    merged.values(),
                    key=lambda run: run.updated_at,
                    reverse=True,
                )
                return ordered[:limit] if limit is not None else ordered
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 요약 목록 조회 실패: %s", error)
                if self.require_database:
                    raise RuntimeError(
                        "WorkflowRun 목록을 PostgreSQL에서 조회할 수 없습니다"
                    ) from error
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 목록 조회에는 PostgreSQL 연결이 필요합니다"
            )

        ordered = sorted(local_runs, key=lambda run: run.updated_at, reverse=True)
        return ordered[:limit] if limit is not None else ordered

    def list(
        self,
        workflow_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[WorkflowRun]:
        return self.list_summaries(workflow_id, limit)

    def list_pending(
        self,
        workflow_ids: Optional[Collection[str]] = None,
    ) -> List[WorkflowRun]:
        """Load only queued/running runs."""
        allowed = set(workflow_ids) if workflow_ids is not None else None
        if self.db_manager is not None:
            try:
                run_ids = self.db_manager.list_pending_workflow_run_ids(
                    sorted(allowed) if allowed is not None else None
                )
                return [self.load(run_id) for run_id in run_ids]
            except Exception as error:
                logger.warning("DB에서 미완료 WorkflowRun 조회 실패: %s", error)
                if self.require_database:
                    raise RuntimeError(
                        "미완료 WorkflowRun을 PostgreSQL에서 조회할 수 없습니다"
                    ) from error
        elif self.require_database:
            raise RuntimeError(
                "미완료 WorkflowRun 조회에는 PostgreSQL 연결이 필요합니다"
            )
        return [
            run
            for run in self.list()
            if run.status in ("queued", "running")
            and (allowed is None or run.workflow_id in allowed)
        ]

    def delete(self, run_id: str) -> bool:
        """Remove one full run."""
        db_deleted = False
        if self.db_manager is not None:
            try:
                db_deleted = self.db_manager.delete_workflow_run(run_id)
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 삭제 실패 (run_id=%s): %s", run_id, error)
                if self.require_database:
                    raise RuntimeError(
                        "WorkflowRun을 PostgreSQL에서 삭제할 수 없습니다"
                    ) from error
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 삭제에는 PostgreSQL 연결이 필요합니다"
            )

        with self._memory_lock:
            existed = self._memory_runs.pop(run_id, None) is not None

        if self._artifact_directory is not None:
            for path in self._artifact_directory.glob(f"{run_id}.*.json.gz"):
                path.unlink(missing_ok=True)

        return existed or db_deleted

    def clear(self) -> int:
        """Delete all stored workflow runs."""
        db_cleared = 0
        if self.db_manager is not None:
            try:
                db_cleared = self.db_manager.clear_workflow_runs()
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 전체 삭제 실패: %s", error)
                if self.require_database:
                    raise RuntimeError(
                        "WorkflowRun 전체 기록을 PostgreSQL에서 삭제할 수 없습니다"
                    ) from error
        elif self.require_database:
            raise RuntimeError(
                "WorkflowRun 전체 삭제에는 PostgreSQL 연결이 필요합니다"
            )

        with self._memory_lock:
            count = len(self._memory_runs)
            self._memory_runs.clear()

        # Also clean up any leftover json files if directory exists
        if self.directory and self.directory.is_dir():
            for path in self.directory.glob("*.json"):
                path.unlink(missing_ok=True)
        if self._artifact_directory and self._artifact_directory.is_dir():
            for path in self._artifact_directory.glob("*.json.gz"):
                path.unlink(missing_ok=True)

        return count if count > 0 else db_cleared


class ResultCache:
    """Zero-I/O in-memory result cache without writing files to local disk."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = directory
        self._memory_cache: Dict[str, Any] = {}
        self._lock = Lock()

    @staticmethod
    def key(module_type: str, payload: Any) -> str:
        canonical = json.dumps(
            {"module_type": module_type, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Any:
        with self._lock:
            return self._memory_cache.get(cache_key)

    def put(self, cache_key: str, value: Any) -> None:
        with self._lock:
            self._memory_cache[cache_key] = value

    def clear(self) -> int:
        with self._lock:
            count = len(self._memory_cache)
            self._memory_cache.clear()
            return count
