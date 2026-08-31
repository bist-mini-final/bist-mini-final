"""Application resource lifecycle owned by the composition layer."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from anyio import to_thread
from fastapi import FastAPI

from backend.bootstrap.application import ApplicationContainer
from backend.core.settings import PROJECT_DIR
from backend.platform.postgres.pool import close_async_pool, close_pool

logger = logging.getLogger("backend.bootstrap.lifecycle")


def create_lifespan(
    container: ApplicationContainer,
    *,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Bind one explicit composition root to the FastAPI lifespan."""

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        started_at = time.perf_counter()
        (PROJECT_DIR / "data").mkdir(parents=True, exist_ok=True)

        module_types = (
            container.runtime.services.module_registry.registered_module_types()
        )
        logger.info("등록된 파이프라인 모듈 %d개", len(module_types))
        try:
            recovered = await to_thread.run_sync(
                container.execution.recover_pending_runs
            )
            if recovered:
                logger.info("미완료 Kubernetes run %d개를 복구했습니다", recovered)
        except Exception:
            logger.warning("Kubernetes run 큐 복구 실패", exc_info=True)

        async def refresh_daily_suggestions() -> None:
            while True:
                try:
                    await to_thread.run_sync(
                        container.domain.chat_suggestions.refresh_if_due
                    )
                except Exception:
                    logger.warning("일일 챗봇 추천 질문 갱신 실패", exc_info=True)
                now = datetime.now(ZoneInfo("Asia/Seoul"))
                next_run = (now + timedelta(days=1)).replace(
                    hour=0,
                    minute=1,
                    second=0,
                    microsecond=0,
                )
                await asyncio.sleep((next_run - now).total_seconds())

        try:
            await to_thread.run_sync(
                lambda: container.domain.chat_suggestions.refresh_if_due(force=True)
            )
        except Exception:
            logger.warning("시작 시 챗봇 추천 질문 생성 실패", exc_info=True)
        suggestions_task = asyncio.create_task(refresh_daily_suggestions())
        logger.info("애플리케이션 초기화 완료 (%.3fs)", time.perf_counter() - started_at)

        try:
            yield
        finally:
            suggestions_task.cancel()
            with suppress(asyncio.CancelledError):
                await suggestions_task
            if on_shutdown is not None:
                await on_shutdown()
            await container.aclose()
            await close_async_pool()
            close_pool()
            logger.info("애플리케이션 리소스를 종료했습니다")

    return lifespan


__all__ = ["create_lifespan"]
