#!/usr/bin/env python3
"""Render the small local ScaledJob template without extra dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


SAFE_NAME = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-replicas", type=int, required=True)
    parser.add_argument("--queue", default="excel-ingestion")
    parser.add_argument("--image", default="bist-workflow-worker:local")
    parser.add_argument("--connection-hash", required=True)
    parser.add_argument("--cpu-request", default="1000m")
    parser.add_argument("--memory-request", default="2Gi")
    parser.add_argument("--cpu-limit", default="2")
    parser.add_argument("--memory-limit", default="3Gi")
    args = parser.parse_args()
    if not 1 <= args.max_replicas <= 100:
        parser.error("max-replicas must be between 1 and 100")
    if not SAFE_NAME.fullmatch(args.queue):
        parser.error("queue must be a Kubernetes-safe lowercase name")
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", args.image):
        parser.error("image contains unsupported characters")
    if not re.fullmatch(r"[a-f0-9]{64}", args.connection_hash):
        parser.error("connection-hash must be a SHA-256 hex digest")

    template = (
        Path(__file__).resolve().parent.parent / "manifests" / "05-scaledjob.yaml"
    ).read_text(encoding="utf-8")
    replacements = {
        "__MAX_REPLICAS__": str(args.max_replicas),
        "__QUEUE__": args.queue,
        "__IMAGE__": args.image,
        "__CONNECTION_HASH__": args.connection_hash,
        "__CPU_REQUEST__": args.cpu_request,
        "__MEMORY_REQUEST__": args.memory_request,
        "__CPU_LIMIT__": args.cpu_limit,
        "__MEMORY_LIMIT__": args.memory_limit,
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    print(template, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
