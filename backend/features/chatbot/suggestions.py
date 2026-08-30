"""Daily, data-aware starter questions for the chat home screen."""

from __future__ import annotations

from datetime import datetime
from secrets import randbelow
from zoneinfo import ZoneInfo

from backend.features.bi.api_services import BiApiServices

from .suggestion_repository import ChatSuggestionRepository


class ChatSuggestionService:
    """Persists one shared set of starter questions per Seoul calendar day."""

    def __init__(
        self,
        repository: ChatSuggestionRepository,
        bi_services: BiApiServices,
    ) -> None:
        self._repository = repository
        self._bi_services = bi_services

    def refresh_if_due(self, *, force: bool = False) -> list[str]:
        seoul_today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        existing = self._repository.list_for_date(seoul_today)
        if existing and not force:
            return existing

        companies = [
            entry.company.display_name
            for entry in self._bi_services.store.list_companies()
        ]
        questions = self._questions_for(companies or ["IBM"], randbelow(10_000))
        self._repository.replace_for_date(seoul_today, questions)
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
