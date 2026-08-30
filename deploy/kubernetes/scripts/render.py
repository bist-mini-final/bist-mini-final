#!/usr/bin/env python3
"""Render every KEDA ScaledJob from the typed product job registry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jobs import ALL_JOBS  # noqa: E402
from jobs.kubernetes import KubernetesWorkerSpec, kubernetes_worker_specs  # noqa: E402


def _indented_query(query: str) -> str:
    return "\n".join(f"          {line}" for line in query.splitlines())


def _args_block(spec: KubernetesWorkerSpec) -> str:
    if not spec.arguments:
        return ""
    return f"            args: {json.dumps(list(spec.arguments))}"


def _volume_blocks(spec: KubernetesWorkerSpec) -> tuple[str, str]:
    if not spec.mount_data_volume:
        return "", ""
    return (
        """            volumeMounts:
              - name: bist-data
                mountPath: /app/data""",
        """        volumes:
          - name: bist-data
            hostPath:
              path: /mnt/bist-data
              type: Directory""",
    )


def render_scaled_job(
    template: str,
    spec: KubernetesWorkerSpec,
    *,
    image: str,
    connection_hash: str,
    max_replicas: int,
    cpu_request: str,
    memory_request: str,
    cpu_limit: str,
    memory_limit: str,
) -> str:
    volume_mounts, volumes = _volume_blocks(spec)
    replacements = {
        "__NAME__": spec.deployment_name,
        "__APP_NAME__": spec.app_name,
        "__QUEUE__": spec.queue_name,
        "__WORKER_MODULE__": spec.worker_module,
        "__ACTIVE_DEADLINE_SECONDS__": str(spec.active_deadline_seconds),
        "__ARGS_BLOCK__": _args_block(spec),
        "__VOLUME_MOUNT_BLOCK__": volume_mounts,
        "__VOLUME_BLOCK__": volumes,
        "__QUERY_BLOCK__": _indented_query(spec.pending_query),
        "__MAX_REPLICAS__": str(
            min(max_replicas, spec.max_replica_count or max_replicas)
        ),
        "__IMAGE__": image,
        "__CONNECTION_HASH__": connection_hash,
        "__CPU_REQUEST__": cpu_request,
        "__MEMORY_REQUEST__": memory_request,
        "__CPU_LIMIT__": cpu_limit,
        "__MEMORY_LIMIT__": memory_limit,
    }
    rendered = template
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    if "__" in rendered:
        raise ValueError(f"unresolved Kubernetes template marker: {spec.deployment_name}")
    return rendered.rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-replicas", type=int, required=True)
    parser.add_argument("--image", default="bist-workflow-worker:local")
    parser.add_argument("--connection-hash", required=True)
    parser.add_argument("--cpu-request", default="1000m")
    parser.add_argument("--memory-request", default="2Gi")
    parser.add_argument("--cpu-limit", default="2")
    parser.add_argument("--memory-limit", default="3Gi")
    args = parser.parse_args()
    if not 1 <= args.max_replicas <= 100:
        parser.error("max-replicas must be between 1 and 100")
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", args.image):
        parser.error("image contains unsupported characters")
    if not re.fullmatch(r"[a-f0-9]{64}", args.connection_hash):
        parser.error("connection-hash must be a SHA-256 hex digest")

    template_path = Path(__file__).resolve().parent.parent / "manifests" / "scaledjob.yaml"
    template = template_path.read_text(encoding="utf-8")
    specs = kubernetes_worker_specs(ALL_JOBS)
    rendered = [
        render_scaled_job(
            template,
            spec,
            image=args.image,
            connection_hash=args.connection_hash,
            max_replicas=args.max_replicas,
            cpu_request=args.cpu_request,
            memory_request=args.memory_request,
            cpu_limit=args.cpu_limit,
            memory_limit=args.memory_limit,
        )
        for spec in specs
    ]
    print("\n---\n".join(rendered) + "\n", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
