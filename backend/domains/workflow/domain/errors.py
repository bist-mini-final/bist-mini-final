"""Workflow-domain failures and safe user-facing formatting."""

from __future__ import annotations

from pydantic import ValidationError


class DagExecutionError(ValueError):
    """Raised when a workflow graph or persisted execution is invalid."""


class DagExecutionCancelled(RuntimeError):
    """Raised after a requested cancellation has been persisted."""


def format_execution_error(error: Exception, *, include_type: bool = False) -> str:
    if isinstance(error, ValidationError):
        messages = [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_url=False)
        ]
        message = "; ".join(messages)
    else:
        message = str(error)
        for marker in ("\n[SQL:", " [SQL:"):
            if marker in message:
                message = message.split(marker, 1)[0].rstrip()
                break
        if include_type:
            message = f"{type(error).__name__}: {message}"
    if len(message) > 4000:
        return message[:4000].rstrip() + "…"
    return message


__all__ = [
    "DagExecutionCancelled",
    "DagExecutionError",
    "format_execution_error",
]

