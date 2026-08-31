"""Compatibility import for BI question persistence."""

from backend.domains.bi.application.errors import (  # noqa: F401
    BiQuestionRegistrationError,
    BiQuestionResetActiveError,
    BiQuestionTransitionError,
)
from backend.domains.bi.infrastructure.postgres.question_repository import *  # noqa: F403
