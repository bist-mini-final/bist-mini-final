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
    parsed_address = ipaddress.ip_address(args.endpoint)
    address = str(parsed_address)
    address_type = "IPv4" if parsed_address.version == 4 else "IPv6"
    template = (
        Path(__file__).with_name("templates") / "postgres-service.yaml"
    ).read_text(encoding="utf-8")
    print(
        template.replace("__DATABASE_ENDPOINT__", address).replace(
            "__ADDRESS_TYPE__",
            address_type,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
