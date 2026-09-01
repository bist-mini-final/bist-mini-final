"""Server-owned workbook identity derived from recognized source-file conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_KEY_STATS_FILE_PATTERN = re.compile(
    r"^SPG_Company_KeyStats_(?P<ordinal>[0-9]{2})_(?P<slug>[a-z0-9_]+?)"
    r"(?:_rank_recalibrated)?$",
    re.IGNORECASE,
)
_DISPLAY_OVERRIDES = {"amesoft": "AmeSoft"}
_UPPERCASE_TOKENS = {"ai", "dx"}


@dataclass(frozen=True, slots=True)
class WorkbookFileIdentity:
    """Identity encoded by a recognized workbook filename contract."""

    company_name: str
    ticker: str = ""


def _display_name(slug: str) -> str:
    override = _DISPLAY_OVERRIDES.get(slug.casefold())
    if override:
        return override
    return " ".join(
        token.upper() if token.casefold() in _UPPERCASE_TOKENS else token.capitalize()
        for token in slug.split("_")
        if token
    )


def workbook_file_identity(file_name: str) -> WorkbookFileIdentity | None:
    """Return a trusted identity only for the numbered KeyStats convention.

    These synthetic workbooks can retain stale template company/ticker cells. The
    numbered filename is the dataset-owned identity; ticker remains empty because
    the filename does not encode one and fabricated symbols are unsafe.
    """

    match = _KEY_STATS_FILE_PATTERN.fullmatch(Path(file_name).stem)
    if match is None:
        return None
    company_name = _display_name(match.group("slug"))
    return WorkbookFileIdentity(company_name=company_name) if company_name else None


__all__ = ["WorkbookFileIdentity", "workbook_file_identity"]
