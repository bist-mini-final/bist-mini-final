"""Reusable heartbeat lifecycle for leased Kubernetes workers."""

from __future__ import annotations

import logging
import os
from threading import Event, Lock, Thread, current_thread
from typing import Callable

LEASE_LOST_EXIT_CODE = 75


class LeaseLostError(RuntimeError):
    """Raised when a worker can no longer prove ownership of its claimed item."""


def terminate_process_on_lease_loss(error: LeaseLostError) -> None:
    """Fail closed so Kubernetes can replace a worker with uncertain ownership."""
    logging.getLogger(__name__).critical("worker lease lost; terminating: %s", error)
    os._exit(LEASE_LOST_EXIT_CODE)


class LeaseHeartbeat:
    """Renew a lease and fail closed when ownership can no longer be proven.

    The short termination grace closes the normal completion race: a terminal
    database update can make the last heartbeat return ``False`` immediately
    before the owning code calls :meth:`stop`. A genuinely stuck worker remains
    armed and is terminated after the grace period.
    """

    def __init__(
        self,
        heartbeat: Callable[[], bool],
        *,
        interval_seconds: float,
        thread_name: str,
        logger: logging.Logger,
        failure_message: str,
        on_lease_lost: Callable[[LeaseLostError], None] | None = None,
        termination_grace_seconds: float = 2.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("heartbeat interval_seconds must be positive")
        if termination_grace_seconds < 0:
            raise ValueError("heartbeat termination_grace_seconds cannot be negative")
        self._heartbeat = heartbeat
        self._interval_seconds = interval_seconds
        self._logger = logger
        self._failure_message = failure_message
        self._on_lease_lost = on_lease_lost
        self._termination_grace_seconds = termination_grace_seconds
        self._stop = Event()
        self._lost = Event()
        self._error_lock = Lock()
        self._error: LeaseLostError | None = None
        self._thread = Thread(
            target=self._run,
            name=thread_name,
            daemon=True,
        )
        self._started = False

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                if not self._heartbeat():
                    self._mark_lost("heartbeat renewal rejected")
                    return
            except Exception as error:
                self._logger.error(self._failure_message, exc_info=True)
                self._mark_lost(
                    f"heartbeat renewal failed: {type(error).__name__}: {error}"
                )
                return

    def _mark_lost(self, reason: str) -> None:
        error = LeaseLostError(f"{self._failure_message}: {reason}")
        with self._error_lock:
            if self._error is not None:
                return
            self._error = error
            self._lost.set()
        self._logger.critical("%s; worker execution is no longer safe", error)
        if self._on_lease_lost is None:
            return
        if self._stop.wait(self._termination_grace_seconds):
            return
        self._on_lease_lost(error)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._stop.set()
        if current_thread() is not self._thread:
            self._thread.join(
                timeout=self._interval_seconds + self._termination_grace_seconds + 1
            )

    @property
    def lease_lost(self) -> bool:
        """Return whether renewal failed or the lease owner changed."""
        return self._lost.is_set()

    def raise_if_lost(self) -> None:
        """Raise the captured ownership failure from cooperative worker code."""
        if not self._lost.is_set():
            return
        with self._error_lock:
            error = self._error
        raise error or LeaseLostError(self._failure_message)

    def __enter__(self) -> "LeaseHeartbeat":
        self.start()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.stop()


__all__ = [
    "LEASE_LOST_EXIT_CODE",
    "LeaseHeartbeat",
    "LeaseLostError",
    "terminate_process_on_lease_loss",
]
