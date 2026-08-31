"""Workbook-level semantic metadata shared by downstream domains."""

from __future__ import annotations

from datetime import date
from enum import StrEnum, unique
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


@unique
class WorkbookAmountScale(StrEnum):
    ONES = "ones"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"


@unique
class WorkbookPeriodKind(StrEnum):
    FY = "fy"
    LTM = "ltm"


@unique
class WorkbookSheetRole(StrEnum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    KEY_STATS = "key_stats"
    UNKNOWN = "unknown"


class WorkbookProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class WorkbookProfileEvidence(WorkbookProfileModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    kind: Literal["currency", "scale", "period", "sheet_role"]
    sheet_name: str = Field(min_length=1, max_length=128)
    cell_coord: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    source_text: str = Field(min_length=1, max_length=2_000)


class WorkbookPeriodProfile(WorkbookProfileModel):
    period_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    kind: WorkbookPeriodKind
    label: str = Field(min_length=1, max_length=64)
    source_label: str = Field(min_length=1, max_length=64)
    end_date: date | None = None
    ordinal: int
    evidence_ids: tuple[str, ...] = ()


class WorkbookSheetProfile(WorkbookProfileModel):
    sheet_name: str = Field(min_length=1, max_length=128)
    role: WorkbookSheetRole
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = ()


class WorkbookProfile(WorkbookProfileModel):
    """Deterministic facts read from one original workbook.

    The profile is intentionally independent of BI cards and metric catalogs so
    chatbot, company comparison, and future spreadsheet consumers can share it.
    """

    schema_version: Literal[1] = 1
    profile_version: str = Field(min_length=1, max_length=32)
    file_name: str = Field(min_length=1, max_length=255)
    workbook_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    index_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    status: Literal["ready", "partial"]
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    amount_scale: WorkbookAmountScale | None = None
    periods: tuple[WorkbookPeriodProfile, ...] = ()
    sheets: tuple[WorkbookSheetProfile, ...] = ()
    evidence: tuple[WorkbookProfileEvidence, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @field_validator("periods")
    @classmethod
    def sort_and_deduplicate_periods(
        cls,
        periods: tuple[WorkbookPeriodProfile, ...],
    ) -> tuple[WorkbookPeriodProfile, ...]:
        identities = {period.period_id for period in periods}
        if len(identities) != len(periods):
            raise ValueError("period_id must be unique")
        return tuple(sorted(periods, key=lambda item: (item.ordinal, item.kind.value)))

    @property
    def is_financially_complete(self) -> bool:
        return bool(self.periods and self.currency and self.amount_scale)


__all__ = [
    "WorkbookAmountScale",
    "WorkbookPeriodKind",
    "WorkbookPeriodProfile",
    "WorkbookProfile",
    "WorkbookProfileEvidence",
    "WorkbookSheetProfile",
    "WorkbookSheetRole",
]
