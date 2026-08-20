#!/usr/bin/env python3
"""Render a cluster Service/EndpointSlice for the existing pgvector container."""

from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    address = str(ipaddress.ip_address(args.endpoint))
    template = (
        Path(__file__).with_name("templates") / "postgres-service.yaml"
    ).read_text(encoding="utf-8")
    print(template.replace("__DATABASE_ENDPOINT__", address), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
