"""Compatibility import for BI metric reading."""

from backend.domains.bi.application.metric_reader import *  # noqa: F403
from backend.domains.bi.infrastructure.integrations.structured_completion import (  # noqa: F401
    BiStructuredCompletionAdapter,
)
