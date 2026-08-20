import hashlib
import json
import logging
from pathlib import Path
from threading import Lock
import time
from typing import Any, Collection, Generic, List, Optional, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from .models import (
    IDENTIFIER_PATTERN,
    WorkflowDocument,
    WorkflowRun,
    WorkflowSaveRequest,
    utc_now_iso,
)
from .history import compact_history_value


ModelType = TypeVar("ModelType", bound=BaseModel)


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

    def list_documents(self) -> List[ModelType]:
        """
        Load all JSON documents from the store in filename order.
        
        Returns:
            List[ModelType]: The validated documents found in the store.
        """
        documents: List[ModelType] = []
        for path in sorted(self.directory.glob("*.json")):
            documents.append(
                self.model_type.model_validate_json(path.read_text(encoding="utf-8"))
            )
        return documents

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
    ACTIVE_WORKFLOW_ID = "workflow"
    DEFAULT_TEMPLATE_ID = "default"

    def __init__(self, directory: Path) -> None:
        self._store = JsonModelStore(directory, WorkflowDocument)

    def save(
        self, workflow_id: str, request: WorkflowSaveRequest
    ) -> WorkflowDocument:
        document = WorkflowDocument(
            id=_validate_identifier(workflow_id),
            name=request.name,
            updated_at=utc_now_iso(),
            graph=request.graph,
        )
        return self._store.write(workflow_id, document)

    def load(self, workflow_id: str) -> WorkflowDocument:
        try:
            return self._store.load(workflow_id)
        except FileNotFoundError:
            if workflow_id != self.ACTIVE_WORKFLOW_ID:
                raise
            template = self._store.load(self.DEFAULT_TEMPLATE_ID)
            return template.model_copy(update={"id": self.ACTIVE_WORKFLOW_ID})

    def list(self) -> List[WorkflowDocument]:
        documents: List[WorkflowDocument] = []
        for path in sorted(self._store.directory.glob("*.json")):
            doc = WorkflowDocument.model_validate_json(path.read_text(encoding="utf-8"))
            # Always use the filename stem as the id so the UI shows actual filenames
            if doc.id != path.stem:
                doc = doc.model_copy(update={"id": path.stem})
            documents.append(doc)
        return documents


logger = logging.getLogger(__name__)


class RunStore:
    def __init__(self, directory: Path, db_manager: Optional[Any] = None) -> None:
        self._store = JsonModelStore(directory, WorkflowRun)
        self._summary_lock = Lock()
        self.db_manager = (
            db_manager
            if db_manager is not None
            and getattr(db_manager, "is_connected", lambda: False)()
            else None
        )

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

    def _write_summary(self, run: WorkflowRun) -> None:
        summary_path = self._store.directory / f"{run.id}.summary.json"
        summary = self._summary(run)
        with self._summary_lock:
            _atomic_write_text(
                summary_path,
                summary.model_dump_json(indent=2) + "\n",
            )

    def save(self, run: WorkflowRun) -> WorkflowRun:
        """
        Persist a workflow run and its compact summary.
        
        Parameters:
        	run (WorkflowRun): The workflow run to persist.
        
        Returns:
        	WorkflowRun: The saved workflow run with its updated timestamp.
        """
        run.updated_at = utc_now_iso()
        saved = self._store.write(run.id, run)
        self._write_summary(run)
        if self.db_manager is not None:
            try:
                self.db_manager.save_workflow_run(run)
            except Exception as error:
                logger.warning("DB에 WorkflowRun 저장 실패 (run_id=%s): %s", run.id, error)
        return saved

    def save_progress(self, run: WorkflowRun, node_id: str) -> WorkflowRun:
        """Persist live node progress without rewriting large full-run payloads."""

        run.updated_at = utc_now_iso()
        self._write_summary(run)
        if self.db_manager is not None:
            try:
                self.db_manager.save_workflow_node_progress(run, node_id)
            except Exception as error:
                logger.warning(
                    "DB에 WorkflowRun 진행률 저장 실패 (run_id=%s, node_id=%s): %s",
                    run.id,
                    node_id,
                    error,
                )
        return run

    def load(self, run_id: str) -> WorkflowRun:
        """Load a complete workflow run by its identifier.
        
        Parameters:
        	run_id (str): Identifier of the workflow run.
        
        Returns:
        	WorkflowRun: The persisted workflow run.
        """
        if self.db_manager is not None:
            try:
                data = self.db_manager.get_workflow_run(run_id)
                if data is not None:
                    return WorkflowRun.model_validate(data)
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 로드 실패 (run_id=%s): %s", run_id, error)
        return self._store.load(run_id)

    def load_summary(self, run_id: str) -> WorkflowRun:
        """Load a compact run snapshot optimized for status polling."""

        if self.db_manager is not None:
            try:
                data = self.db_manager.get_workflow_run_summary(run_id)
                if data is not None:
                    return WorkflowRun.model_validate(data)
            except Exception as error:
                logger.warning(
                    "DB에서 WorkflowRun 요약 로드 실패 (run_id=%s): %s",
                    run_id,
                    error,
                )
        summary_path = self._store.directory / f"{_validate_identifier(run_id)}.summary.json"
        if summary_path.is_file():
            return WorkflowRun.model_validate_json(
                summary_path.read_text(encoding="utf-8")
            )
        return self._summary(self.load(run_id))

    def list_summaries(
        self,
        workflow_id: Optional[str] = None,
    ) -> List[WorkflowRun]:
        """List compact run snapshots without loading full node payloads."""

        local_runs: List[WorkflowRun] = []
        for path in sorted(self._store.directory.glob("*.summary.json")):
            try:
                run = WorkflowRun.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except FileNotFoundError:
                continue
            if workflow_id is None or run.workflow_id == workflow_id:
                local_runs.append(run)

        if self.db_manager is not None:
            try:
                records = self.db_manager.list_workflow_run_summaries(workflow_id)
                database_runs = [
                    WorkflowRun.model_validate(record) for record in records
                ]
                # A database reconnect, restore, or partial migration can leave valid
                # local summaries that are not present in PostgreSQL. Keep those runs
                # visible in history while preferring the newest snapshot for duplicate
                # IDs. This also prevents a single unrelated DB row from hiding every
                # locally persisted ingestion run.
                merged = {run.id: run for run in local_runs}
                for run in database_runs:
                    existing = merged.get(run.id)
                    if existing is None or run.updated_at >= existing.updated_at:
                        merged[run.id] = run
                return list(merged.values())
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 요약 목록 조회 실패: %s", error)

        return local_runs

    def list(self, workflow_id: Optional[str] = None) -> List[WorkflowRun]:
        """
        List workflow run summaries, optionally filtered by workflow identifier.
        
        Parameters:
        	workflow_id (Optional[str]): Identifier of the workflow whose runs should be included.
        
        Returns:
        	List[WorkflowRun]: Loaded workflow run summaries, filtered when a workflow identifier is provided.
        """
        if self.db_manager is not None:
            try:
                records = self.db_manager.list_workflow_runs(workflow_id)
                runs: List[WorkflowRun] = []
                for rec in records:
                    summary = WorkflowRun.model_validate(rec)
                    summary.runtime_inputs = compact_history_value(summary.runtime_inputs)
                    for state in summary.nodes.values():
                        state.input_payload = compact_history_value(state.input_payload)
                        state.output = compact_history_value(state.output)
                    runs.append(summary)
                return runs
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 목록 조회 실패: %s", error)

        runs: List[WorkflowRun] = []
        for path in sorted(self._store.directory.glob("*.summary.json")):
            try:
                runs.append(
                    WorkflowRun.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except FileNotFoundError:
                # A concurrent delete removes the summary before the full run.
                # Treat it as absent from this snapshot rather than a server error.
                continue
        if workflow_id is None:
            return runs
        return [run for run in runs if run.workflow_id == workflow_id]

    def list_pending(
        self,
        workflow_ids: Optional[Collection[str]] = None,
    ) -> List[WorkflowRun]:
        """Load only queued/running runs, using an ID-only database query first."""

        allowed = set(workflow_ids) if workflow_ids is not None else None
        if self.db_manager is not None:
            try:
                run_ids = self.db_manager.list_pending_workflow_run_ids(
                    sorted(allowed) if allowed is not None else None
                )
                return [self.load(run_id) for run_id in run_ids]
            except Exception as error:
                logger.warning("DB에서 미완료 WorkflowRun 조회 실패: %s", error)
        return [
            run
            for run in self.list()
            if run.status in ("queued", "running")
            and (allowed is None or run.workflow_id in allowed)
        ]

    def delete(self, run_id: str) -> bool:
        """Remove one full run and its compact summary."""
        db_deleted = False
        if self.db_manager is not None:
            try:
                db_deleted = self.db_manager.delete_workflow_run(run_id)
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 삭제 실패 (run_id=%s): %s", run_id, error)

        summary_path = self._store.directory / (
            f"{_validate_identifier(run_id)}.summary.json"
        )
        removed = False
        with self._summary_lock:
            if summary_path.is_file():
                summary_path.unlink()
                removed = True
        removed = self._store.delete(run_id) or removed or db_deleted
        return removed

    def clear(self) -> int:
        """Delete all stored workflow runs and their summary files.
        
        Returns:
            int: The number of full workflow runs deleted.
        """
        db_cleared = 0
        if self.db_manager is not None:
            try:
                db_cleared = self.db_manager.clear_workflow_runs()
            except Exception as error:
                logger.warning("DB에서 WorkflowRun 전체 삭제 실패: %s", error)

        full_run_paths = [
            path
            for path in self._store.directory.glob("*.json")
            if not path.name.endswith(".summary.json")
        ]
        for path in full_run_paths:
            path.unlink()
        for path in self._store.directory.glob("*.summary.json"):
            path.unlink()
        return len(full_run_paths) if len(full_run_paths) > 0 else db_cleared


class ResultCache:
    """Content-addressed JSON result cache for deterministic module calls."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._lock = Lock()
        self.directory.mkdir(parents=True, exist_ok=True)

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
        path = self.directory / f"{cache_key}.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value

    def put(self, cache_key: str, value: Any) -> None:
        """Store a value in the result cache under the specified key.
        
        Parameters:
        	cache_key (str): Content-addressed key for the cached value
        	value (Any): JSON-serializable value to cache
        """
        path = self.directory / f"{cache_key}.json"
        with self._lock:
            _atomic_write_text(
                path,
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
            )

    def clear(self) -> int:
        """
        Remove all JSON files from the store directory.
        
        Returns:
        	int: The number of files removed.
        """
        removed = 0
        with self._lock:
            for path in self.directory.glob("*.json"):
                path.unlink()
                removed += 1
        return removed
