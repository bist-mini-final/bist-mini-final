"""Errors raised by the PostgreSQL vector storage adapter."""


class PgVectorStoreError(RuntimeError):
    """Raised when a pgvector database operation fails."""


__all__ = ["PgVectorStoreError"]
