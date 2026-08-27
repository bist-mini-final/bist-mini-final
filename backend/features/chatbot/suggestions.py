"""Daily, data-aware starter questions for the chat home screen."""

from __future__ import annotations

from datetime import datetime
from secrets import randbelow
from zoneinfo import ZoneInfo

from backend.features.bi.api_services import BiApiServices
from backend.storage.db_manager import DatabaseManager


class ChatSuggestionService:
    """Persists one shared set of starter questions per Seoul calendar day."""

    def __init__(self, database: DatabaseManager, bi_services: BiApiServices) -> None:
        self._database = database
        self._bi_services = bi_services

    def refresh_if_due(self, *, force: bool = False) -> list[str]:
        seoul_today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        today = seoul_today.isoformat()
        with self._database._raw_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT question FROM chat_suggested_questions WHERE suggestion_date = %s ORDER BY position",
                    (today,),
                )
                existing = [row[0] for row in cursor.fetchall()]
                if existing and not force:
                    return existing

                if force:
                    cursor.execute(
                        "DELETE FROM chat_suggested_questions WHERE suggestion_date = %s",
                        (today,),
                    )

                companies = [entry.company.display_name for entry in self._bi_services.store.list_companies()]
                questions = self._questions_for(companies or ["IBM"], randbelow(10_000))
                cursor.executemany(
                    """INSERT INTO chat_suggested_questions (suggestion_date, position, question)
                    VALUES (%s, %s, %s) ON CONFLICT (suggestion_date, position) DO NOTHING""",
                    [(today, position, question) for position, question in enumerate(questions)],
                )
            connection.commit()
        return questions

    @staticmethod
    def _questions_for(companies: list[str], seed: int) -> list[str]:
        templates = [
            "{company}의 최근 연도 매출과 영업이익을 비교해줘.",
            "{company}의 총자산과 총부채는 각각 얼마인가요?",
            "{company}의 현금흐름 추이를 차트로 보여줘.",
            "{company}의 매출 성장률과 수익성 변화를 알려줘.",
            "{company}의 부채와 자본 규모를 비교해줘.",
        ]
        template_start = seed % len(templates)
        company_start = (seed // len(templates)) % len(companies)
        return [
            templates[(template_start + offset) % len(templates)].format(
                company=companies[(company_start + offset) % len(companies)],
            )
            for offset in range(3)
        ]
