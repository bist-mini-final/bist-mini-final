"""Typed cell-evidence contracts shared by workflow and product consumers."""

from pydantic import BaseModel, ConfigDict, Field


class CellEvidenceDTO(BaseModel):
    """One verified spreadsheet cell selected as support for an answer."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    index_id: str | None = None
    workbook_hash: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    company_name: str | None = None
    sheet_name: str = Field(min_length=1)
    cell_coord: str = Field(pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
    row_header: list[str] = Field(default_factory=list)
    column_header: list[str] = Field(default_factory=list)
    cell_value: str = Field(min_length=1)
    source_text: str = Field(min_length=1)


class GroundedAnswerDTO(BaseModel):
    """Answer body and its independently transported verified evidence."""

    model_config = ConfigDict(extra="forbid")

    answer_markdown: str = Field(min_length=1)
    evidence: list[CellEvidenceDTO] = Field(default_factory=list)


__all__ = ["CellEvidenceDTO", "GroundedAnswerDTO"]
