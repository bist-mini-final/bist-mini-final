"""Application service for durable company-comparison snapshots."""

from __future__ import annotations

from typing import Protocol

from backend.domains.bi.domain.models import BiDashboardSnapshot
from backend.domains.company_comparison.application.snapshot_builder import (
    FORECAST_VERSION,
    SCORING_VERSION,
    CompanyComparisonSnapshotBuilder,
)
from backend.domains.company_comparison.domain.errors import (
    ComparisonDataError,
    ComparisonSnapshotIntegrityError,
)
from backend.domains.company_comparison.domain.models import CompanyComparisonSnapshot
from backend.domains.data_sources.domain.cell_values import extract_resolved_cell_value
from backend.shared.application.snapshots import (
    VersionedSnapshotRecord,
    VersionedSnapshotRepository,
)

SNAPSHOT_DOMAIN = "company-comparison"
SNAPSHOT_SCOPE = "global"


class CompanyComparisonSourcePort(Protocol):
    async def load_current_snapshots(self) -> tuple[BiDashboardSnapshot, ...]: ...


class CompanyComparisonService:
    def __init__(
        self,
        source: CompanyComparisonSourcePort,
        snapshots: VersionedSnapshotRepository,
        builder: CompanyComparisonSnapshotBuilder | None = None,
    ) -> None:
        self._source = source
        self._snapshots = snapshots
        self._builder = builder or CompanyComparisonSnapshotBuilder()

    async def current(self) -> CompanyComparisonSnapshot | None:
        record = await self._snapshots.get_current(
            domain=SNAPSHOT_DOMAIN,
            scope_key=SNAPSHOT_SCOPE,
        )
        if record is None:
            return None
        snapshot = CompanyComparisonSnapshot.model_validate(record.payload)
        if (
            record.snapshot_id != snapshot.snapshot.snapshot_id
            or record.schema_version != snapshot.schema_version
            or record.source_fingerprint != snapshot.snapshot.source_fingerprint
            or record.generated_at != snapshot.snapshot.generated_at
        ):
            raise ComparisonSnapshotIntegrityError(
                "stored company-comparison envelope does not match its payload"
            )
        return snapshot

    async def current_or_refresh(self) -> CompanyComparisonSnapshot | None:
        current = await self.current()
        try:
            return await self.refresh()
        except ComparisonDataError:
            return current

    async def refresh(self) -> CompanyComparisonSnapshot:
        source_snapshots = await self._source.load_current_snapshots()
        fingerprint = self._builder.source_fingerprint(source_snapshots)
        current = await self.current()
        if (
            current is not None
            and current.snapshot.source_fingerprint == fingerprint
            and current.snapshot.scoring_version == SCORING_VERSION
            and current.snapshot.forecast_version == FORECAST_VERSION
            and all(
                extract_resolved_cell_value(item.source_text) is not None
                for item in current.evidence
            )
        ):
            return current

        snapshot = self._builder.build(source_snapshots)
        await self._snapshots.publish(
            VersionedSnapshotRecord(
                snapshot_id=snapshot.snapshot.snapshot_id,
                domain=SNAPSHOT_DOMAIN,
                scope_key=SNAPSHOT_SCOPE,
                schema_version=snapshot.schema_version,
                source_fingerprint=snapshot.snapshot.source_fingerprint,
                payload=snapshot.model_dump(mode="json"),
                generated_at=snapshot.snapshot.generated_at,
            )
        )
        return snapshot


__all__ = [
    "SNAPSHOT_DOMAIN",
    "SNAPSHOT_SCOPE",
    "CompanyComparisonService",
    "CompanyComparisonSourcePort",
]
