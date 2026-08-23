import asyncio
import unittest
from dataclasses import dataclass

from backend.core.state_stream import SharedStateStream


@dataclass(frozen=True, slots=True)
class Snapshot:
    version: int
    terminal: bool = False


class SharedStateStreamTests(unittest.TestCase):
    def test_one_loader_is_shared_by_concurrent_subscribers(self) -> None:
        calls = 0

        def load(_key: str) -> Snapshot:
            nonlocal calls
            calls += 1
            return Snapshot(version=2, terminal=True)

        async def scenario() -> tuple[list[int], list[int]]:
            stream = SharedStateStream(
                load,
                fingerprint=lambda state: state.version,
                terminal=lambda state: state.terminal,
                interval_seconds=0.001,
            )

            async def collect() -> list[int]:
                return [
                    state.version
                    async for state in stream.subscribe(
                        "run-1",
                        initial=Snapshot(version=1),
                    )
                ]

            return await asyncio.gather(collect(), collect())

        first, second = asyncio.run(scenario())

        self.assertEqual(first, [1, 2])
        self.assertEqual(second, [1, 2])
        self.assertEqual(calls, 1)

    def test_terminal_initial_state_is_delivered_before_close(self) -> None:
        async def scenario() -> list[int]:
            stream = SharedStateStream(
                lambda _key: Snapshot(version=99, terminal=True),
                fingerprint=lambda state: state.version,
                terminal=lambda state: state.terminal,
                interval_seconds=0.001,
            )
            return [
                state.version
                async for state in stream.subscribe(
                    "job-1",
                    initial=Snapshot(version=3, terminal=True),
                )
            ]

        self.assertEqual(asyncio.run(scenario()), [3])


if __name__ == "__main__":
    unittest.main()
