import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Type, TypeVar

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


def _validate_identifier(value: str) -> str:
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
        path = self._path(document_id)
        temporary_path = path.with_suffix(".json.tmp")
        serialized = document.model_dump_json(indent=2)
        with self._lock:
            temporary_path.write_text(serialized + "\n", encoding="utf-8")
            temporary_path.replace(path)
        return document

    def list_documents(self) -> List[ModelType]:
        documents: List[ModelType] = []
        for path in sorted(self.directory.glob("*.json")):
            documents.append(
                self.model_type.model_validate_json(path.read_text(encoding="utf-8"))
            )
        return documents

    def clear(self) -> int:
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
        return self._store.list_documents()

    def delete(self, workflow_id: str) -> None:
        if workflow_id in (self.ACTIVE_WORKFLOW_ID, self.DEFAULT_TEMPLATE_ID):
            raise ValueError("The current/default workflow cannot be deleted")
        self._store.delete(workflow_id)


class RunStore:
    def __init__(self, directory: Path) -> None:
        self._store = JsonModelStore(directory, WorkflowRun)
        self._summary_lock = Lock()

    def save(self, run: WorkflowRun) -> WorkflowRun:
        run.updated_at = utc_now_iso()
        saved = self._store.write(run.id, run)
        summary = run.model_copy(deep=True)
        summary.runtime_inputs = compact_history_value(run.runtime_inputs)
        for state in summary.nodes.values():
            state.input_payload = compact_history_value(state.input_payload)
            state.output = compact_history_value(state.output)
        summary_path = self._store.directory / f"{run.id}.summary.json"
        temporary_path = summary_path.with_name(f"{summary_path.name}.tmp")
        with self._summary_lock:
            temporary_path.write_text(
                summary.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(summary_path)
        return saved

    def load(self, run_id: str) -> WorkflowRun:
        return self._store.load(run_id)

    def list(self, workflow_id: Optional[str] = None) -> List[WorkflowRun]:
        runs = [
            WorkflowRun.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._store.directory.glob("*.summary.json"))
        ]
        if workflow_id is None:
            return runs
        return [run for run in runs if run.workflow_id == workflow_id]

    def clear(self) -> int:
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
        path = self.directory / f"{cache_key}.json"
        temporary_path = path.with_suffix(".json.tmp")
        with self._lock:
            temporary_path.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(path)

    def clear(self) -> int:
        removed = 0
        with self._lock:
            for path in self.directory.glob("*.json"):
                path.unlink()
                removed += 1
        return removed
