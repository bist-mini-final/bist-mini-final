from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Hashable
from dataclasses import dataclass, field
from typing import Generic, TypeVar, cast

from anyio import to_thread

KeyT = TypeVar("KeyT", bound=Hashable)
StateT = TypeVar("StateT")

_END = object()


@dataclass(slots=True)
class _StateChannel(Generic[StateT]):
    subscribers: set[asyncio.Queue[StateT | BaseException | object]] = field(
        default_factory=set
    )
    task: asyncio.Task[None] | None = None
    latest: StateT | None = None
    has_latest: bool = False


class SharedStateStream(Generic[KeyT, StateT]):
    """Fan out one persisted-state observer to every SSE client for a key.

    The synchronous loader runs outside the event loop. Slow or duplicated browser
    connections therefore neither block API request handling nor multiply database
    polling for the same workflow/job inside one API process.
    """

    def __init__(
        self,
        loader: Callable[[KeyT], StateT],
        *,
        fingerprint: Callable[[StateT], object],
        terminal: Callable[[StateT], bool],
        interval_seconds: float = 0.5,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._loader = loader
        self._fingerprint = fingerprint
        self._terminal = terminal
        self._interval_seconds = interval_seconds
        self._channels: dict[KeyT, _StateChannel[StateT]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        key: KeyT,
        *,
        initial: StateT | None = None,
    ) -> AsyncIterator[StateT]:
        queue: asyncio.Queue[StateT | BaseException | object] = asyncio.Queue(
            maxsize=2
        )
        async with self._lock:
            channel = self._channels.get(key)
            if channel is None:
                channel = _StateChannel()
                if initial is not None:
                    channel.latest = initial
                    channel.has_latest = True
                self._channels[key] = channel
                channel.task = asyncio.create_task(self._pump(key, channel))
            channel.subscribers.add(queue)
            if channel.has_latest:
                queue.put_nowait(cast(StateT, channel.latest))

        try:
            while True:
                item = await queue.get()
                if item is _END:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield cast(StateT, item)
        finally:
            await self._unsubscribe(key, channel, queue)

    async def _pump(self, key: KeyT, channel: _StateChannel[StateT]) -> None:
        previous_fingerprint: object = object()
        use_initial = channel.has_latest
        if channel.has_latest:
            previous_fingerprint = self._fingerprint(cast(StateT, channel.latest))
        try:
            while True:
                if use_initial:
                    state = cast(StateT, channel.latest)
                    use_initial = False
                else:
                    state = await to_thread.run_sync(self._loader, key)
                current_fingerprint = self._fingerprint(state)
                if current_fingerprint != previous_fingerprint:
                    previous_fingerprint = current_fingerprint
                    channel.latest = state
                    channel.has_latest = True
                    self._broadcast(channel, state)
                if self._terminal(state):
                    self._broadcast(channel, _END)
                    return
                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            return
        except BaseException as error:
            self._broadcast(channel, error)
        finally:
            async with self._lock:
                if self._channels.get(key) is channel:
                    self._channels.pop(key, None)

    @staticmethod
    def _broadcast(
        channel: _StateChannel[StateT],
        item: StateT | BaseException | object,
    ) -> None:
        for queue in tuple(channel.subscribers):
            if item is not _END and not isinstance(item, BaseException):
                while not queue.empty():
                    queue.get_nowait()
            elif queue.full():
                queue.get_nowait()
            queue.put_nowait(item)

    async def _unsubscribe(
        self,
        key: KeyT,
        channel: _StateChannel[StateT],
        queue: asyncio.Queue[StateT | BaseException | object],
    ) -> None:
        async with self._lock:
            channel.subscribers.discard(queue)
            if channel.subscribers or self._channels.get(key) is not channel:
                return
            if channel.task is not None and not channel.task.done():
                channel.task.cancel()
            self._channels.pop(key, None)
