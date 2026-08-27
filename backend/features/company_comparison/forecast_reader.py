from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence

from backend.features.bi.models import BiDashboardSnapshot, BiEvidence, MetricId

from .calculator import CompanyForecastData, ComparisonObservation


class ForecastCellStorePort(Protocol):
    def fetch_cells_by_metadata(
        self,
        cell_identifiers: list[str],
        workbook_hash: str | None = None,
        company_name: str | None = None,
        collection_name: str | None = None,
        limit: int = 50,
        cell_references: list[dict[str, str | None]] | None = None,
    ) -> Sequence[Mapping[str, Any]]: ...


FORECAST_CELLS = {
    2026: {MetricId.REVENUE: "N33", MetricId.OPERATING_INCOME: "N42"},
    2027: {MetricId.REVENUE: "O33", MetricId.OPERATING_INCOME: "O42"},
    2028: {MetricId.REVENUE: "P33", MetricId.OPERATING_INCOME: "P42"},
}


class ComparisonForecastReader:
    """Read exact forecast cells from the selected workbook's pgvector index."""

    def __init__(self, cell_store: ForecastCellStorePort) -> None:
        self._cell_store = cell_store

    def read_many(
        self,
        snapshots: tuple[BiDashboardSnapshot, ...],
    ) -> tuple[CompanyForecastData, ...]:
        return tuple(self._read(snapshot) for snapshot in snapshots)

    def _read(self, snapshot: BiDashboardSnapshot) -> CompanyForecastData:
        coordinates = [
            coordinate
            for metrics in FORECAST_CELLS.values()
            for coordinate in metrics.values()
        ]
        rows = self._cell_store.fetch_cells_by_metadata(
            cell_identifiers=coordinates,
            workbook_hash=snapshot.source.workbook_hash,
            collection_name=str(snapshot.source.index_id),
            limit=len(coordinates),
            cell_references=[
                {"sheet_name": "Key_Stats", "cell_coord": coordinate}
                for coordinate in coordinates
            ],
        )
        by_coordinate = {
            str(row.get("cell_coord") or "").upper(): row for row in rows
        }
        observations: dict[int, dict[MetricId, ComparisonObservation]] = {}
        for year, metrics in FORECAST_CELLS.items():
            yearly: dict[MetricId, ComparisonObservation] = {}
            for metric_id, coordinate in metrics.items():
                row = by_coordinate.get(coordinate)
                if row is None:
                    continue
                raw_value = str(row.get("cell_value") or "").strip()
                try:
                    value = Decimal(raw_value)
                except (InvalidOperation, ValueError):
                    continue
                source_text = str(row.get("source_text") or "").strip()
                if not source_text:
                    source_text = (
                        f"Key_Stats {coordinate} | {metric_id.value} | "
                        f"{year} estimate | {raw_value}"
                    )
                yearly[metric_id] = ComparisonObservation(
                    normalized_value=value,
                    evidence=(
                        BiEvidence(
                            cell_id=str(row.get("cell_id") or f"KS Cell {coordinate}"),
                            sheet_name="Key_Stats",
                            cell_coord=coordinate,
                            source_text=source_text,
                        ),
                    ),
                    origin="rag",
                )
            if yearly:
                observations[year] = yearly
        return CompanyForecastData(
            company_id=str(snapshot.company.company_id),
            observations=observations,
        )


__all__ = ["ComparisonForecastReader", "ForecastCellStorePort"]
