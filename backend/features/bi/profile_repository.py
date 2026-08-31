"""Compatibility import for BI profile persistence."""

from backend.domains.bi.application.errors import BiDocumentProfileRepositoryError  # noqa: F401
from backend.domains.bi.infrastructure.postgres.profile_repository import *  # noqa: F403
