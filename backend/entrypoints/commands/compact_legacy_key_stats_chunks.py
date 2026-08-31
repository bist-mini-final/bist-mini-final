"""Process adapter for the legacy Key Stats compaction command."""

from __future__ import annotations

from collections.abc import Sequence

from backend.bootstrap.commands.compact_legacy_key_stats_chunks import main as run_command


def main(argv: Sequence[str] | None = None) -> int:
    return run_command(argv)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
