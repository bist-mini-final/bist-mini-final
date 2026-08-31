"""Compatibility imports for :mod:`backend.shared.application.leases`."""

from backend.shared.application.leases import (
    LeaseHeartbeat,
    LeaseLostError,
    terminate_process_on_lease_loss,
)

__all__ = [
    "LeaseHeartbeat",
    "LeaseLostError",
    "terminate_process_on_lease_loss",
]
