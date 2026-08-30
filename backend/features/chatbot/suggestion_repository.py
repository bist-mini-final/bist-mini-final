"""PostgreSQL adapter for the daily chatbot suggestion set."""

from __future__ import annotations

from datetime import date

from backend.shared.infrastructure.database import (
    DatabaseUrlProvider,
    SyncPostgresRepository,
)


class ChatSuggestionRepository(SyncPostgresRepository):
    def __init__(self, database: str | DatabaseUrlProvider) -> None:
        super().__init__(database)

    def list_for_date(self, suggestion_date: date) -> list[str]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT question FROM chat_suggested_questions "
                    "WHERE suggestion_date = %s ORDER BY position",
                    (suggestion_date,),
                )
                return [str(row[0]) for row in cursor.fetchall()]

    def replace_for_date(
        self,
        suggestion_date: date,
        questions: list[str],
    ) -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM chat_suggested_questions "
                    "WHERE suggestion_date = %s",
                    (suggestion_date,),
                )
                cursor.executemany(
                    "INSERT INTO chat_suggested_questions "
                    "(suggestion_date, position, question) VALUES (%s, %s, %s)",
                    [
                        (suggestion_date, position, question)
                        for position, question in enumerate(questions)
                    ],
                )


__all__ = ["ChatSuggestionRepository"]
