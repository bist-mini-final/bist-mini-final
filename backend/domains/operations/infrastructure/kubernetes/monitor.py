"""Read-only Kubernetes API adapter with local kubectl fallback."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Callable, Mapping, Sequence

import httpx

from backend.domains.operations.application import WorkflowLeaseReader
from backend.domains.operations.domain import (
    KubernetesResourceSummary,
    KubernetesWorkloadSnapshot,
    WorkflowLeaseSummary,
)

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _condition(status: Mapping[str, Any], condition_type: str) -> Mapping[str, Any]:
    conditions = status.get("conditions")
    if not isinstance(conditions, list):
        return {}
    return next(
        (
            item
            for item in conditions
            if isinstance(item, Mapping) and item.get("type") == condition_type
        ),
        {},
    )


def _boolean_condition(status: Mapping[str, Any], condition_type: str) -> bool | None:
    value = _condition(status, condition_type).get("status")
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def _timestamp(metadata: Mapping[str, Any]) -> datetime | None:
    raw = metadata.get("creationTimestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_message(status: Mapping[str, Any]) -> str | None:
    for condition_type in ("Ready", "Failed", "Complete"):
        condition = _condition(status, condition_type)
        message = condition.get("message") or condition.get("reason")
        if isinstance(message, str) and message.strip():
            return message.strip()[:240]
    return None


def _resource(item: Mapping[str, Any]) -> KubernetesResourceSummary | None:
    metadata = item.get("metadata")
    status = item.get("status")
    if not isinstance(metadata, Mapping) or not isinstance(status, Mapping):
        return None
    name = metadata.get("name")
    namespace = metadata.get("namespace")
    kind = item.get("kind")
    if not isinstance(name, str) or not isinstance(namespace, str):
        return None

    if kind == "ScaledJob":
        ready = _boolean_condition(status, "Ready")
        active = _boolean_condition(status, "Active")
        display_status = "Ready" if ready else "NotReady"
        return KubernetesResourceSummary(
            kind=kind,
            name=name,
            namespace=namespace,
            status=display_status,
            ready=ready,
            active=active,
            created_at=_timestamp(metadata),
            message=_safe_message(status),
        )
    if kind == "Job":
        succeeded = int(status.get("succeeded") or 0)
        failed = int(status.get("failed") or 0)
        active_count = int(status.get("active") or 0)
        display_status = (
            "Failed"
            if failed
            else "Complete"
            if succeeded
            else "Running"
            if active_count
            else "Pending"
        )
        return KubernetesResourceSummary(
            kind=kind,
            name=name,
            namespace=namespace,
            status=display_status,
            ready=succeeded > 0,
            active=active_count > 0,
            succeeded=succeeded,
            failed=failed,
            created_at=_timestamp(metadata),
            message=_safe_message(status),
        )
    if kind == "Pod":
        phase = status.get("phase")
        container_statuses = status.get("containerStatuses")
        statuses = container_statuses if isinstance(container_statuses, list) else []
        ready = bool(statuses) and all(
            bool(container.get("ready"))
            for container in statuses
            if isinstance(container, Mapping)
        )
        return KubernetesResourceSummary(
            kind=kind,
            name=name,
            namespace=namespace,
            status=str(phase or "Unknown"),
            ready=ready,
            active=phase == "Running",
            created_at=_timestamp(metadata),
            message=_safe_message(status),
        )
    return None


class KubernetesMonitor:
    """Collect workload state without exposing logs, secrets, or mutations."""

    _SERVICE_ACCOUNT = Path("/var/run/secrets/kubernetes.io/serviceaccount")

    def __init__(
        self,
        *,
        namespace: str | None = None,
        command_runner: CommandRunner = subprocess.run,
        cache_seconds: float = 2.0,
        queue_reader: WorkflowLeaseReader | None = None,
        lease_stale_seconds: int = 180,
    ) -> None:
        self.namespace = namespace or os.getenv("KUBERNETES_NAMESPACE", "bist-batch")
        self._command_runner = command_runner
        self._cache_seconds = max(0.0, cache_seconds)
        self._queue_reader = queue_reader
        self._lease_stale_seconds = max(1, lease_stale_seconds)
        self._cache_lock = Lock()
        self._cached_at = 0.0
        self._cached: KubernetesWorkloadSnapshot | None = None

    def snapshot(self) -> KubernetesWorkloadSnapshot:
        with self._cache_lock:
            now = monotonic()
            if self._cached is not None and now - self._cached_at < self._cache_seconds:
                return self._cached.model_copy(deep=True)
            snapshot = self._collect()
            self._cached = snapshot
            self._cached_at = now
            return snapshot.model_copy(deep=True)

    def _collect(self) -> KubernetesWorkloadSnapshot:
        try:
            if os.getenv("KUBERNETES_SERVICE_HOST"):
                context, items = self._in_cluster_items()
                source = "in_cluster"
            else:
                context, items = self._kubectl_items()
                source = "kubectl"
            resources = [resource for item in items if (resource := _resource(item))]
            queue_available, workflow_runs, queue_error = self._workflow_leases(
                resources
            )
            return KubernetesWorkloadSnapshot(
                available=True,
                source=source,
                namespace=self.namespace,
                context=context,
                collected_at=datetime.now(UTC),
                scaled_jobs=[item for item in resources if item.kind == "ScaledJob"],
                jobs=[item for item in resources if item.kind == "Job"],
                pods=[item for item in resources if item.kind == "Pod"],
                queue_available=queue_available,
                workflow_runs=workflow_runs,
                queue_error=queue_error,
            )
        except Exception as error:
            queue_available, workflow_runs, queue_error = self._workflow_leases([])
            return KubernetesWorkloadSnapshot(
                available=False,
                source="unavailable",
                namespace=self.namespace,
                collected_at=datetime.now(UTC),
                queue_available=queue_available,
                workflow_runs=workflow_runs,
                queue_error=queue_error,
                error=f"{type(error).__name__}: {str(error)[:220]}",
            )

    def _workflow_leases(
        self,
        resources: list[KubernetesResourceSummary],
    ) -> tuple[bool, list[WorkflowLeaseSummary], str | None]:
        if self._queue_reader is None:
            return False, [], "queue reader is not configured"
        resource_names = tuple(resource.name for resource in resources)
        try:
            rows = self._queue_reader.list_active_workflow_leases(
                stale_after_seconds=self._lease_stale_seconds,
                limit=100,
            )
            leases: list[WorkflowLeaseSummary] = []
            for row in rows:
                worker_id = row.get("worker_id")
                matching_resources = (
                    name
                    for name in resource_names
                    if isinstance(worker_id, str)
                    and (
                        name == worker_id
                        or name.startswith(worker_id)
                        or worker_id.startswith(name)
                    )
                )
                matched_resource = max(
                    matching_resources,
                    key=lambda name: (name == worker_id, len(name)),
                    default=None,
                )
                leases.append(
                    WorkflowLeaseSummary.model_validate(
                        {**row, "kubernetes_resource": matched_resource}
                    )
                )
            return True, leases, None
        except Exception as error:
            return False, [], f"{type(error).__name__}: {str(error)[:220]}"

    def _in_cluster_items(self) -> tuple[str, list[Mapping[str, Any]]]:
        host = os.environ["KUBERNETES_SERVICE_HOST"]
        port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        token = (self._SERVICE_ACCOUNT / "token").read_text(encoding="utf-8").strip()
        ca_file = self._SERVICE_ACCOUNT / "ca.crt"
        paths = (
            f"/apis/keda.sh/v1alpha1/namespaces/{self.namespace}/scaledjobs",
            f"/apis/batch/v1/namespaces/{self.namespace}/jobs",
            f"/api/v1/namespaces/{self.namespace}/pods",
        )
        items: list[Mapping[str, Any]] = []
        with httpx.Client(
            base_url=f"https://{host}:{port}",
            headers={"Authorization": f"Bearer {token}"},
            verify=str(ca_file),
            timeout=8.0,
        ) as client:
            for path in paths:
                response = client.get(path)
                response.raise_for_status()
                items.extend(self._items(response.json()))
        return "in-cluster", items

    def _kubectl_items(self) -> tuple[str | None, list[Mapping[str, Any]]]:
        binary = os.getenv("KUBECTL_BIN") or shutil.which("kubectl")
        if not binary:
            raise FileNotFoundError("kubectl executable was not found")
        context_result = self._run((binary, "config", "current-context"))
        context = context_result.stdout.strip() or None
        result = self._run(
            (
                binary,
                "get",
                "scaledjobs.keda.sh,jobs,pods",
                "--namespace",
                self.namespace,
                "--output",
                "json",
            )
        )
        return context, self._items(json.loads(result.stdout))

    def _run(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        completed = self._command_runner(
            list(command),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            reason = (completed.stderr or completed.stdout or "kubectl failed").strip()
            raise RuntimeError(reason[:240])
        return completed

    @staticmethod
    def _items(payload: Any) -> list[Mapping[str, Any]]:
        if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
            raise ValueError("Kubernetes list response has no items")
        return [item for item in payload["items"] if isinstance(item, Mapping)]


__all__ = ["KubernetesMonitor"]
