#!/usr/bin/env python3
"""Derive a safe local Job concurrency from Docker Desktop capacity."""

from __future__ import annotations

import argparse
import json
import math
import subprocess


def docker_capacity() -> tuple[float, float]:
    output = subprocess.check_output(
        ["docker", "info", "--format", "{{json .}}"],
        text=True,
    )
    info = json.loads(output)
    cpus = float(info.get("NCPU") or 1)
    memory_gib = float(info.get("MemTotal") or 0) / (1024**3)
    return cpus, memory_gib


def recommended_concurrency(
    cpus: float,
    memory_gib: float,
    *,
    cpu_per_job: float,
    memory_per_job_gib: float,
    reserve_cpu: float,
    reserve_memory_gib: float,
    hard_cap: int,
) -> int:
    cpu_slots = math.floor(max(0.0, cpus - reserve_cpu) / cpu_per_job)
    memory_slots = math.floor(
        max(0.0, memory_gib - reserve_memory_gib) / memory_per_job_gib
    )
    return max(1, min(cpu_slots, memory_slots, hard_cap))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-per-job", type=float, default=1.0)
    parser.add_argument("--memory-per-job-gib", type=float, default=2.0)
    parser.add_argument("--reserve-cpu", type=float, default=1.0)
    parser.add_argument("--reserve-memory-gib", type=float, default=2.0)
    parser.add_argument("--hard-cap", type=int, default=10)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    cpus, memory_gib = docker_capacity()
    concurrency = recommended_concurrency(
        cpus,
        memory_gib,
        cpu_per_job=args.cpu_per_job,
        memory_per_job_gib=args.memory_per_job_gib,
        reserve_cpu=args.reserve_cpu,
        reserve_memory_gib=args.reserve_memory_gib,
        hard_cap=args.hard_cap,
    )
    if args.details:
        print(
            json.dumps(
                {
                    "docker_cpus": cpus,
                    "docker_memory_gib": round(memory_gib, 2),
                    "recommended_max_jobs": concurrency,
                }
            )
        )
    else:
        print(concurrency)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
