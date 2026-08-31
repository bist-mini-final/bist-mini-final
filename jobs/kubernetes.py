"""Project product jobs into Kubernetes worker deployment specifications."""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Iterable

from .base import DagJobDefinition, JobDefinition, WorkerJobDefinition


@dataclass(frozen=True)
class KubernetesWorkerSpec:
    deployment_name: str
    app_name: str
    queue_name: str
    worker_module: str
    pending_query: str
    active_deadline_seconds: int
    arguments: tuple[str, ...] = ()
    mount_data_volume: bool = False
    max_replica_count: int | None = None


def _workflow_pending_query(queue_name: str) -> str:
    return f"""
        SELECT COUNT(*) FROM workflow_runs
        WHERE queue_name = '{queue_name}'
          AND cancel_requested = FALSE
          AND ((status = 'queued' AND available_at <= NOW())
            OR (status = 'running' AND (heartbeat_at IS NULL
              OR heartbeat_at < NOW() - (180 * INTERVAL '1 second'))))
    """


def kubernetes_worker_specs(
    jobs: Iterable[JobDefinition],
) -> tuple[KubernetesWorkerSpec, ...]:
    """Return one shared worker per DAG queue and one per leased worker job."""
    definitions = tuple(jobs)
    dag_queues = sorted(
        {job.queue_name for job in definitions if isinstance(job, DagJobDefinition)}
    )
    specs = [
        KubernetesWorkerSpec(
            deployment_name=(
                "workflow-worker"
                if queue_name == "workflow-core"
                else f"{queue_name}-worker"
            ),
            app_name="workflow-worker",
            queue_name=queue_name,
            worker_module="backend.entrypoints.worker",
            arguments=("workflow", "--queue", queue_name),
            pending_query=dedent(_workflow_pending_query(queue_name)).strip(),
            active_deadline_seconds=21_600,
            mount_data_volume=True,
            max_replica_count=None,
        )
        for queue_name in dag_queues
    ]
    specs.extend(
        KubernetesWorkerSpec(
            deployment_name=job.kubernetes.deployment_name,
            app_name=f"{job.kubernetes.deployment_name}-worker",
            queue_name=job.queue_name,
            worker_module=job.worker_module,
            arguments=(job.worker_kind,),
            pending_query=dedent(job.kubernetes.pending_query).strip(),
            active_deadline_seconds=job.kubernetes.active_deadline_seconds,
            mount_data_volume=job.kubernetes.mount_data_volume,
            max_replica_count=job.kubernetes.max_replica_count,
        )
        for job in definitions
        if isinstance(job, WorkerJobDefinition)
    )
    return tuple(specs)


__all__ = ["KubernetesWorkerSpec", "kubernetes_worker_specs"]
