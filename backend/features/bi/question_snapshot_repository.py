"""Compatibility import for BI question snapshot persistence."""

from backend.domains.bi.application.errors import BiQuestionSnapshotRepositoryError  # noqa: F401
from backend.domains.bi.infrastructure.postgres.question_snapshot_repository import *  # noqa: F403
