"""Optional cross-pod change notifications for persisted SSE state."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class StateStreamBroker(Protocol):
    """Publish lightweight state-change hints without transporting domain data."""

    async def publish(self, topic: str) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[None]: ...

    async def aclose(self) -> None: ...


class RedisStateStreamBroker:
    """Redis Pub/Sub broker used to wake SSE streams on other API Pods.

    PostgreSQL remains the source of truth. Redis carries only a topic signal, so
    a delayed, duplicated, or missed Pub/Sub message cannot expose stale state;
    the receiving API process reloads the persisted record before emitting SSE.
    """

    def __init__(self, url: str, *, channel_prefix: str = "bist:state") -> None:
        self._url = url
        self._channel_prefix = channel_prefix.rstrip(":")
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> Any:
        async with self._client_lock:
            if self._client is None:
                from redis.asyncio import Redis

                self._client = Redis.from_url(
                    self._url,
                    encoding="utf-8",
                    decode_responses=True,
                    health_check_interval=30,
                )
            return self._client

    def _channel(self, topic: str) -> str:
        return f"{self._channel_prefix}:{topic}"

    async def publish(self, topic: str) -> None:
        try:
            client = await self._get_client()
            await client.publish(self._channel(topic), "changed")
        except Exception:
            # Polling continues to provide a correct, though less immediate,
            # fallback when Redis is temporarily unavailable.
            logger.warning("Redis SSE change publish failed", exc_info=True)

    async def _messages(self, topic: str) -> AsyncIterator[None]:
        pubsub = None
        try:
            client = await self._get_client()
            pubsub = client.pubsub()
            await pubsub.subscribe(self._channel(topic))
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is not None:
                    yield None
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Redis SSE change subscription failed", exc_info=True)
        finally:
            if pubsub is not None:
                with suppress(Exception):
                    await pubsub.unsubscribe(self._channel(topic))
                with suppress(Exception):
                    await pubsub.aclose()

    def subscribe(self, topic: str) -> AsyncIterator[None]:
        return self._messages(topic)

    async def aclose(self) -> None:
        if self._client is None:
            return
        client = self._client
        self._client = None
        with suppress(Exception):
            await client.aclose()


def create_state_stream_broker(redis_url: str | None) -> StateStreamBroker | None:
    """Return a broker only when the deployment explicitly configures Redis."""

    normalized = (redis_url or "").strip()
    if not normalized:
        return None
    return RedisStateStreamBroker(normalized)


__all__ = [
    "RedisStateStreamBroker",
    "StateStreamBroker",
    "create_state_stream_broker",
]
