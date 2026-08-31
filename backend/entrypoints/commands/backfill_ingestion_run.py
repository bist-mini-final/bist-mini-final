"""Process adapter for ingestion-history backfill."""

from __future__ import annotations

from collections.abc import Sequence

from backend.bootstrap.commands.backfill_ingestion_run import main as run_command


def main(argv: Sequence[str] | None = None) -> int:
    return run_command(argv)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
