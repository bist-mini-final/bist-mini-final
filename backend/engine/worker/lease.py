"""Reusable heartbeat lifecycle for leased Kubernetes workers."""

from __future__ import annotations

import logging
from threading import Event, Thread
from typing import Callable


class LeaseHeartbeat:
    """Run one lease-renewal callback until stopped or ownership is lost."""

    def __init__(
        self,
        heartbeat: Callable[[], bool],
        *,
        interval_seconds: float,
        thread_name: str,
        logger: logging.Logger,
        failure_message: str,
    ) -> None:
        self._heartbeat = heartbeat
        self._interval_seconds = interval_seconds
        self._logger = logger
        self._failure_message = failure_message
        self._stop = Event()
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
                    return
            except Exception:
                self._logger.warning(self._failure_message, exc_info=True)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._stop.set()
        self._thread.join(timeout=self._interval_seconds + 1)

    def __enter__(self) -> "LeaseHeartbeat":
        self.start()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.stop()


__all__ = ["LeaseHeartbeat"]
