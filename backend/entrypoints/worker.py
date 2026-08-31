"""Unified Kubernetes/local one-shot worker process entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from backend.bootstrap.workers import registered_worker_kinds, run_worker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=registered_worker_kinds())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args, remaining = _parser().parse_known_args(argv)
    return run_worker(args.kind, remaining)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
