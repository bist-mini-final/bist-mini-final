"""Opt-in Redis integration coverage for cross-Pod SSE state notifications."""

from __future__ import annotations

import asyncio
import os
import unittest

from backend.core.state_stream import SharedStateStream
from backend.core.state_stream_broker import RedisStateStreamBroker

REDIS_URL = os.getenv("REDIS_URL")


@unittest.skipUnless(REDIS_URL, "set REDIS_URL to run the Redis SSE integration test")
class RedisStateStreamIntegrationTests(unittest.TestCase):
    def test_redis_notification_wakes_a_second_api_process_stream(self) -> None:
        async def scenario() -> None:
            assert REDIS_URL is not None
            persisted = {"status": "queued", "revision": 0}
            publisher = RedisStateStreamBroker(REDIS_URL, channel_prefix="bist:test")
            subscriber = RedisStateStreamBroker(REDIS_URL, channel_prefix="bist:test")
            first = SharedStateStream(
                lambda _key: dict(persisted),
                fingerprint=lambda state: state["revision"],
                terminal=lambda state: state["status"] == "completed",
                interval_seconds=0.01,
                broker=publisher,
                topic_prefix="workflow-run",
            )
            second = SharedStateStream(
                lambda _key: dict(persisted),
                fingerprint=lambda state: state["revision"],
                terminal=lambda state: state["status"] == "completed",
                # A 60s fallback makes the broker delivery observable.
                interval_seconds=60,
                broker=subscriber,
                topic_prefix="workflow-run",
            )
            first_events = first.subscribe("run-redis", initial=dict(persisted))
            second_events = second.subscribe("run-redis", initial=dict(persisted))
            try:
                self.assertEqual((await anext(first_events))["revision"], 0)
                self.assertEqual((await anext(second_events))["revision"], 0)
                # Give both Pub/Sub subscriptions time to complete before publishing.
                await asyncio.sleep(0.05)
                persisted.update(status="running", revision=1)
                received = await asyncio.wait_for(anext(second_events), timeout=2.0)
                self.assertEqual(received, {"status": "running", "revision": 1})
            finally:
                await first_events.aclose()
                await second_events.aclose()
                await publisher.aclose()
                await subscriber.aclose()

        asyncio.run(scenario())
