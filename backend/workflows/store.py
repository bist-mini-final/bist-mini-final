import hashlib
import json
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Type, TypeVar
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


class JsonModelStore:
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

    def delete(self, document_id: str) -> None:
        path = self._path(document_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        with self._lock:
            path.unlink()


class WorkflowStore:
    ACTIVE_WORKFLOW_ID = "workflow"
    DEFAULT_TEMPLATE_ID = "default"

    def __init__(self, directory: Path) -> None:
        self._store = JsonModelStore(directory, WorkflowDocument)

    def save(
        self, workflow_id: str, request: WorkflowSaveRequest
    ) -> WorkflowDocument:
        node_ids = {node.id for node in request.graph.nodes}
        # Keep a stale client-side edge from making the whole workflow invalid.
        # This also repairs documents produced by older canvas versions.
        graph = request.graph.model_copy(
            update={
                "edges": [
                    edge
                    for edge in request.graph.edges
                    if edge.source in node_ids and edge.target in node_ids
                ]
            }
        )
        document = WorkflowDocument(
            id=_validate_identifier(workflow_id),
            name=request.name,
            updated_at=utc_now_iso(),
            graph=graph,
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

    def delete(self, workflow_id: str) -> None:
        if workflow_id in (self.ACTIVE_WORKFLOW_ID, self.DEFAULT_TEMPLATE_ID):
            raise ValueError("The current/default workflow cannot be deleted")
        self._store.delete(workflow_id)


class RunStore:
    def __init__(self, directory: Path) -> None:
        self._store = JsonModelStore(directory, WorkflowRun)
        self._summary_lock = Lock()

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
        summary = run.model_copy(deep=True)
        summary.runtime_inputs = compact_history_value(run.runtime_inputs)
        for state in summary.nodes.values():
            state.input_payload = compact_history_value(state.input_payload)
            state.output = compact_history_value(state.output)
        summary_path = self._store.directory / f"{run.id}.summary.json"
        with self._summary_lock:
            _atomic_write_text(
                summary_path,
                summary.model_dump_json(indent=2) + "\n",
            )
        return saved

    def load(self, run_id: str) -> WorkflowRun:
        """Load a complete workflow run by its identifier.
        
        Parameters:
        	run_id (str): Identifier of the workflow run.
        
        Returns:
        	WorkflowRun: The persisted workflow run.
        """
        return self._store.load(run_id)

    def list(self, workflow_id: Optional[str] = None) -> List[WorkflowRun]:
        """
        List workflow run summaries, optionally filtered by workflow identifier.
        
        Parameters:
        	workflow_id (Optional[str]): Identifier of the workflow whose runs should be included.
        
        Returns:
        	List[WorkflowRun]: Loaded workflow run summaries, filtered when a workflow identifier is provided.
        """
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

    def delete(self, run_id: str) -> bool:
        """Remove one full run and its compact summary."""

        summary_path = self._store.directory / (
            f"{_validate_identifier(run_id)}.summary.json"
        )
        removed = False
        with self._summary_lock:
            if summary_path.is_file():
                summary_path.unlink()
                removed = True
        removed = self._store.delete(run_id) or removed
        return removed

    def clear(self) -> int:
        """Delete all stored workflow runs and their summary files.
        
        Returns:
            int: The number of full workflow runs deleted.
        """
        full_run_paths = [
            path
            for path in self._store.directory.glob("*.json")
            if not path.name.endswith(".summary.json")
        ]
        for path in full_run_paths:
            path.unlink()
        for path in self._store.directory.glob("*.summary.json"):
            path.unlink()
        return len(full_run_paths)


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
