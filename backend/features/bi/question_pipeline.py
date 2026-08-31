"""Compatibility import for the BI question pipeline."""

from backend.domains.bi.application.errors import BiQuestionSourceError  # noqa: F401
from backend.domains.bi.infrastructure.integrations.question_pipeline import *  # noqa: F403
