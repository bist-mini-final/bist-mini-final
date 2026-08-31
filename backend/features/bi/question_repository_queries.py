"""Compatibility import for BI question queries."""

from backend.domains.bi.application.errors import BiQuestionRepositoryError  # noqa: F401
from backend.domains.bi.infrastructure.postgres.question_repository_queries import *  # noqa: F403
