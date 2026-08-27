from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.job_routes import create_job_router
from backend.providers.kubernetes_monitor import KubernetesMonitor


def _runner(command: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
    if "current-context" in command:
        return subprocess.CompletedProcess(command, 0, "k3d-bist-local\n", "")
    payload = {
        "items": [
            {
                "apiVersion": "keda.sh/v1alpha1",
                "kind": "ScaledJob",
                "metadata": {
                    "name": "workflow-core",
                    "namespace": "bist-batch",
                    "creationTimestamp": "2026-08-27T00:00:00Z",
                },
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            },
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {"name": "workflow-core-abc", "namespace": "bist-batch"},
                "status": {"active": 1},
            },
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": "workflow-core-abc-pod", "namespace": "bist-batch"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{"ready": True}],
                },
            },
        ]
    }
    return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")


def test_kubectl_snapshot_is_normalized_for_the_read_only_portal(monkeypatch: Any) -> None:
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monitor = KubernetesMonitor(command_runner=_runner, cache_seconds=0)

    snapshot = monitor.snapshot()

    assert snapshot.available is True
    assert snapshot.source == "kubectl"
    assert snapshot.context == "k3d-bist-local"
    assert snapshot.scaled_jobs[0].status == "Ready"
    assert snapshot.jobs[0].status == "Running"
    assert snapshot.pods[0].ready is True


def test_monitor_failure_is_a_safe_snapshot(monkeypatch: Any) -> None:
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)

    def failed_runner(
        command: Sequence[str],
        **_: Any,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "cluster unavailable")

    snapshot = KubernetesMonitor(
        command_runner=failed_runner,
        cache_seconds=0,
    ).snapshot()

    assert snapshot.available is False
    assert snapshot.source == "unavailable"
    assert "cluster unavailable" in (snapshot.error or "")


def test_jobs_endpoint_is_get_only(monkeypatch: Any) -> None:
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    app = FastAPI()
    app.include_router(
        create_job_router(KubernetesMonitor(command_runner=_runner, cache_seconds=0))
    )
    client = TestClient(app)

    response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json()["scaled_jobs"][0]["name"] == "workflow-core"
    assert client.post("/jobs").status_code == 405


def test_backend_manifest_uses_minimum_read_only_rbac_and_correct_probes() -> None:
    root = Path(__file__).resolve().parents[2]
    rbac = (root / "deploy/kubernetes/manifests/01-backend-rbac.yaml").read_text(
        encoding="utf-8"
    )
    deployment = (root / "deploy/kubernetes/manifests/02-backend.yaml").read_text(
        encoding="utf-8"
    )

    assert 'verbs: ["get", "list", "watch"]' in rbac
    assert "create" not in rbac
    assert "delete" not in rbac
    assert "serviceAccountName: backend-api" in deployment
    assert "readinessProbe:\n            httpGet:\n              path: /readyz" in deployment
    assert "livenessProbe:\n            httpGet:\n              path: /livez" in deployment
