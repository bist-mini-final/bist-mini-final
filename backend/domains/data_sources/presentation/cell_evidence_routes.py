"""HTTP presentation for reader cell-evidence verification."""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.domains.data_sources.application.evidence import (
    CellEvidenceQuery,
    CellEvidenceService,
)


class CellEvidenceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet_name: str = Field(min_length=1, max_length=200)
    cell_coord: str = Field(min_length=2, max_length=20)
    company_name: str = Field(default="", max_length=200)
    workbook_hash: str = Field(default="", max_length=64)
    index_id: str = Field(default="", max_length=200)
    file_name: str = Field(default="", max_length=500)
    cell_value: str = Field(default="", max_length=500)

    def to_query(self) -> CellEvidenceQuery:
        return CellEvidenceQuery(**self.model_dump())


class CellEvidenceBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CellEvidenceResolveRequest] = Field(min_length=1, max_length=100)


def create_cell_evidence_router(service: CellEvidenceService) -> APIRouter:
    router = APIRouter(prefix="/evidence", tags=["답변 근거 검증"])

    @router.get(
        "/cells/resolve",
        summary="Reader 답변의 셀 근거와 원본 시트 이미지 연결",
    )
    def resolve_cell_evidence(
        sheet_name: str = Query(min_length=1, max_length=200),
        cell_coord: str = Query(min_length=2, max_length=20),
        company_name: str = Query(default="", max_length=200),
        workbook_hash: str = Query(default="", max_length=64),
        index_id: str = Query(default="", max_length=200),
        file_name: str = Query(default="", max_length=500),
        cell_value: str = Query(default="", max_length=500),
    ) -> dict[str, Any]:
        return service.resolve(
            CellEvidenceQuery(
                sheet_name=sheet_name,
                cell_coord=cell_coord,
                company_name=company_name,
                workbook_hash=workbook_hash,
                index_id=index_id,
                file_name=file_name,
                cell_value=cell_value,
            )
        )

    @router.post(
        "/cells/resolve-batch",
        summary="같은 답변에서 참조한 시트 셀 근거 일괄 연결",
    )
    def resolve_cell_evidence_batch(payload: CellEvidenceBatchRequest) -> dict[str, Any]:
        return {"items": service.resolve_many([item.to_query() for item in payload.items])}

    return router


__all__ = ["create_cell_evidence_router"]
