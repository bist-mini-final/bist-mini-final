from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from backend.core.state_stream import SharedStateStream
from backend.core.state_stream_broker import create_state_stream_broker


class InMemoryStateStreamBroker:
    """Test broker with the same notification-only semantics as Redis Pub/Sub."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[None]]] = {}

    async def publish(self, topic: str) -> None:
        for queue in tuple(self._subscribers.get(topic, ())):
            queue.put_nowait(None)

    async def _messages(self, topic: str) -> AsyncIterator[None]:
        queue: asyncio.Queue[None] = asyncio.Queue()
        self._subscribers.setdefault(topic, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[topic].discard(queue)

    def subscribe(self, topic: str) -> AsyncIterator[None]:
        return self._messages(topic)

    async def aclose(self) -> None:
        return None


def test_redis_broker_is_opt_in() -> None:
    assert create_state_stream_broker("") is None
    assert create_state_stream_broker(None) is None
    assert create_state_stream_broker("redis://redis:6379/0") is not None


def test_cross_process_notification_reloads_persisted_state() -> None:
    async def scenario() -> None:
        persisted = {"status": "queued", "revision": 0}
        broker = InMemoryStateStreamBroker()
        first = SharedStateStream(
            lambda _key: dict(persisted),
            fingerprint=lambda state: state["revision"],
            terminal=lambda state: state["status"] == "completed",
            interval_seconds=0.01,
            broker=broker,
            topic_prefix="workflow-run",
        )
        second = SharedStateStream(
            lambda _key: dict(persisted),
            fingerprint=lambda state: state["revision"],
            terminal=lambda state: state["status"] == "completed",
            # The broker, not this slow fallback poll, must deliver the update.
            interval_seconds=60,
            broker=broker,
            topic_prefix="workflow-run",
        )
        first_events = first.subscribe("run-1", initial=dict(persisted))
        second_events = second.subscribe("run-1", initial=dict(persisted))
        try:
            assert (await anext(first_events))["revision"] == 0
            assert (await anext(second_events))["revision"] == 0
            await asyncio.sleep(0.02)
            persisted.update(status="running", revision=1)
            received = await asyncio.wait_for(anext(second_events), timeout=0.5)
            assert received == {"status": "running", "revision": 1}
        finally:
            await first_events.aclose()
            await second_events.aclose()

    asyncio.run(scenario())
