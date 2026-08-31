from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol


class BiCompanyCatalogPort(Protocol):
    def list_companies(self) -> Sequence[Any]: ...

    def get_current(self, company_id: Any) -> Any | None: ...


class ChatSuggestionRepositoryPort(Protocol):
    def list_for_date(self, suggestion_date: date) -> list[str]: ...

    def replace_for_date(
        self,
        suggestion_date: date,
        questions: list[str],
    ) -> None: ...


__all__ = ["BiCompanyCatalogPort", "ChatSuggestionRepositoryPort"]
