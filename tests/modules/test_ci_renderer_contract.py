"""Run the CI renderer invocation against its current CLI contract."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

from jobs import ALL_JOBS
from jobs.kubernetes import kubernetes_worker_specs

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_ci_scaledjob_command_renders_every_worker_with_image_revision() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    step = next(
        step
        for step in workflow["jobs"]["backend-unit-tests"]["steps"]
        if step["name"] == "Render Kubernetes ScaledJobs"
    )
    command = shlex.split(
        step["run"].split("> /tmp/bist-scaledjobs.yaml", 1)[0].replace("\\\n", ""),
        comments=True,
    )
    assert command[:3] == ["uv", "run", "python"]
    result = subprocess.run(
        [sys.executable, *command[3:]],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    documents = list(yaml.safe_load_all(result.stdout))
    expected = kubernetes_worker_specs(ALL_JOBS)
    assert {document["metadata"]["name"] for document in documents} == {
        spec.deployment_name for spec in expected
    }
    assert len(documents) == len(expected)
    for document in documents:
        assert document["kind"] == "ScaledJob"
        annotations = document["metadata"]["annotations"]
        revision = annotations["bist.ai/image-revision"]
        assert re.fullmatch(r"[a-f0-9]{64}", revision)
        pod_annotations = document["spec"]["jobTargetRef"]["template"]["metadata"][
            "annotations"
        ]
        assert pod_annotations["bist.ai/image-revision"] == revision
