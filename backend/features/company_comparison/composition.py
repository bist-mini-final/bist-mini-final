"""Composition boundary for the company-comparison domain."""

from __future__ import annotations

from backend.features.bi.api_services import BiApiStorePort
from backend.storage.versioned_snapshot_store import PostgresVersionedSnapshotRepository

from .service import CompanyComparisonService


def create_company_comparison_service(
    source: BiApiStorePort,
    *,
    database_url: str,
) -> CompanyComparisonService:
    return CompanyComparisonService(
        source=source,
        snapshots=PostgresVersionedSnapshotRepository(database_url),
    )


__all__ = ["create_company_comparison_service"]
