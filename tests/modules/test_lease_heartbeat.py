from __future__ import annotations

import logging
from threading import Event

import pytest

from backend.engine.worker.lease import LeaseHeartbeat, LeaseLostError


def _heartbeat(
    callback,
    *,
    on_lease_lost=None,
    grace: float = 0.0,
) -> LeaseHeartbeat:
    return LeaseHeartbeat(
        callback,
        interval_seconds=0.01,
        thread_name="test-lease-heartbeat",
        logger=logging.getLogger(__name__),
        failure_message="test lease heartbeat failed",
        on_lease_lost=on_lease_lost,
        termination_grace_seconds=grace,
    )


def test_rejected_renewal_marks_lease_lost_and_invokes_abort() -> None:
    aborted = Event()
    heartbeat = _heartbeat(
        lambda: False,
        on_lease_lost=lambda _error: aborted.set(),
    )

    heartbeat.start()
    assert aborted.wait(1)
    assert heartbeat.lease_lost
    with pytest.raises(LeaseLostError, match="renewal rejected"):
        heartbeat.raise_if_lost()
    heartbeat.stop()


def test_renewal_exception_fails_closed() -> None:
    aborted = Event()

    def fail() -> bool:
        raise ConnectionError("database unavailable")

    heartbeat = _heartbeat(
        fail,
        on_lease_lost=lambda _error: aborted.set(),
    )

    heartbeat.start()
    assert aborted.wait(1)
    with pytest.raises(LeaseLostError, match="ConnectionError"):
        heartbeat.raise_if_lost()
    heartbeat.stop()


def test_normal_stop_during_grace_suppresses_abort() -> None:
    lost = Event()
    aborted = Event()

    def reject() -> bool:
        lost.set()
        return False

    heartbeat = _heartbeat(
        reject,
        on_lease_lost=lambda _error: aborted.set(),
        grace=0.2,
    )

    heartbeat.start()
    assert lost.wait(1)
    heartbeat.stop()
    assert heartbeat.lease_lost
    assert not aborted.is_set()


def test_healthy_heartbeat_stops_without_loss() -> None:
    renewed = Event()

    def renew() -> bool:
        renewed.set()
        return True

    heartbeat = _heartbeat(renew)
    heartbeat.start()
    assert renewed.wait(1)
    heartbeat.stop()
    assert not heartbeat.lease_lost
    heartbeat.raise_if_lost()
