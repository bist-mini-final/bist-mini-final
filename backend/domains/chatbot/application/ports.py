from __future__ import annotations

from datetime import date
from typing import Protocol


class ChatSuggestionRepositoryPort(Protocol):
    def list_for_date(self, suggestion_date: date) -> list[str]: ...

    def replace_for_date(
        self,
        suggestion_date: date,
        questions: list[str],
    ) -> None: ...


__all__ = ["ChatSuggestionRepositoryPort"]

