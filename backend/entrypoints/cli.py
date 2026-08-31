"""Unified management-command process entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from importlib import import_module
from types import MappingProxyType
from typing import cast

CommandMain = Callable[[Sequence[str] | None], int]

COMMAND_TARGETS = MappingProxyType(
    {
        "run-module": "backend.cli.run_module:main",
        "generate-module-docs": "backend.cli.generate_module_docs:main",
        "backfill-ingestion-run": "backend.cli.backfill_ingestion_run:main",
        "compact-legacy-chunks": "backend.cli.compact_legacy_key_stats_chunks:main",
    }
)


def _load_command(command: str) -> CommandMain:
    target = COMMAND_TARGETS[command]
    module_name, function_name = target.split(":", 1)
    function = getattr(import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"CLI entrypoint가 callable이 아닙니다: {target}")
    return cast(CommandMain, function)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=tuple(COMMAND_TARGETS))
    args, remaining = parser.parse_known_args(argv)
    return _load_command(args.command)(remaining)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["COMMAND_TARGETS", "main"]
