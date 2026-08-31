"""Compatibility exports for benchmark schema initialization."""

from backend.domains.benchmark.infrastructure.postgres import (
    BENCHMARK_SCHEMA_SQL,
    BenchmarkSchemaError,
    ensure_benchmark_schema,
)

__all__ = ["BENCHMARK_SCHEMA_SQL", "BenchmarkSchemaError", "ensure_benchmark_schema"]
