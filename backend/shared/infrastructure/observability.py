"""Compatibility imports for :mod:`backend.shared.application.observability`."""

from backend.shared.application.observability import (
    ObservabilityContext,
    bind_observability_context,
    current_observability_context,
    observability_log_extra,
)

__all__ = [
    "ObservabilityContext",
    "bind_observability_context",
    "current_observability_context",
    "observability_log_extra",
]
