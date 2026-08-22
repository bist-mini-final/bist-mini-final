"""OpenTelemetry tracer provider and instrumentation utilities for BIST-Mini."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

# Initialize single global tracer provider if not already configured
_provider: Optional[TracerProvider] = None
try:
    current_provider = trace.get_tracer_provider()
    if not isinstance(current_provider, TracerProvider):
        _provider = TracerProvider()
        trace.set_tracer_provider(_provider)
except Exception:
    _provider = TracerProvider()
    trace.set_tracer_provider(_provider)

tracer = trace.get_tracer("bist.workflow.engine", "2.0.0")


@contextmanager
def trace_node_execution(
    workflow_id: str,
    run_id: str,
    node_id: str,
    module_type: str,
    batch_index: int,
):
    """Context manager wrapping node execution in an OpenTelemetry Span."""
    span_name = f"dag_node:{node_id} ({module_type})"
    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("workflow.id", workflow_id)
        span.set_attribute("workflow.run_id", run_id)
        span.set_attribute("dag.node_id", node_id)
        span.set_attribute("dag.module_type", module_type)
        span.set_attribute("dag.batch_index", batch_index)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
