"""Adapter from the BI application facade to comparison source snapshots."""

from backend.domains.bi.application import BiApiStorePort
from backend.domains.bi.domain.models import BiDashboardSnapshot


class CompanyComparisonBiSourceAdapter:
    def __init__(self, source: BiApiStorePort) -> None:
        self._source = source

    async def load_current_snapshots(self) -> tuple[BiDashboardSnapshot, ...]:
        entries = await self._source.list_companies_async()
        company_ids = tuple(
            entry.company.company_id
            for entry in entries
            if entry.current_snapshot_id is not None
        )
        loaded = await self._source.get_current_many_async(company_ids)
        return tuple(
            loaded[company_id]
            for company_id in company_ids
            if company_id in loaded
        )


__all__ = ["CompanyComparisonBiSourceAdapter"]
