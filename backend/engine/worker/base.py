"""Compatibility imports for :mod:`backend.shared.application.workers`."""

from backend.shared.application.workers import (
    LeasedWorker,
    WorkerLeaseSpec,
    default_worker_id,
)

__all__ = ["LeasedWorker", "WorkerLeaseSpec", "default_worker_id"]
