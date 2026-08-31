"""Filesystem adapter for bundled benchmark-set documents."""

from __future__ import annotations

import json
from pathlib import Path

from backend.domains.benchmark.application.ports import (
    BenchmarkSetDocument,
    BenchmarkSetSourceError,
)

BENCHMARK_SET_NAMES = {
    "semantic-decomposition-core-6": "6유형 핵심 6문항",
    "semantic-decomposition-holdout-18": "분해 홀드아웃 18문항",
    "semantic-routing-comparison-24": "라우팅 비교 24문항",
    "semantic-safety-holdout-30": "안전성 홀드아웃 30문항",
}


class LocalBenchmarkSetSource:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def list_documents(self) -> tuple[BenchmarkSetDocument, ...]:
        documents: list[BenchmarkSetDocument] = []
        for path in sorted(self._directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise BenchmarkSetSourceError(
                    f"벤치마크 세트 파일을 읽을 수 없습니다 ({path.name}): {error}"
                ) from error
            if not isinstance(payload, list) or not all(
                isinstance(item, dict) for item in payload
            ):
                raise BenchmarkSetSourceError(
                    f"벤치마크 세트는 객체 배열이어야 합니다 ({path.name})"
                )
            documents.append(
                BenchmarkSetDocument(
                    set_id=path.stem,
                    name=BENCHMARK_SET_NAMES.get(path.stem, path.stem),
                    cases=tuple(payload),
                )
            )
        return tuple(documents)


__all__ = ["BENCHMARK_SET_NAMES", "LocalBenchmarkSetSource"]
