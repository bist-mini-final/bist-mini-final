"""Composition boundary for company-comparison domain adapters."""

from __future__ import annotations

from backend.domains.bi.application import BiApiStorePort
from backend.domains.company_comparison.application import CompanyComparisonService
from backend.storage.versioned_snapshot_store import PostgresVersionedSnapshotRepository


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
