"""Execute one backend module from a JSON request without the frontend.

Examples:
    python -m backend.tools.run_module json_transformer --request request.json
    printf '{"input":{"any_json":{"a":1}},"config":{}}' \
      | python -m backend.tools.run_module json_transformer
    python -m backend.tools.run_module json_transformer --contract
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from ..answer_cache import AnswerCacheRepository
from ..config import CACHE_DIR
from ..module_registry import ModuleRegistry
from ..modules.base import ModuleExecutionError, ModuleExecutionRequestDTO


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one registered backend module with JSON input/config DTOs."
    )
    parser.add_argument("module_type", help="GET /api/modules에 노출되는 모듈 type")
    parser.add_argument(
        "--request",
        type=Path,
        help="{input, config} JSON 파일. 생략하면 표준 입력에서 읽습니다.",
    )
    parser.add_argument(
        "--contract",
        action="store_true",
        help="모듈 계약만 JSON으로 출력하고 실행하지 않습니다.",
    )
    return parser


def _read_request(path: Path | None) -> Any:
    raw = path.read_text(encoding="utf-8") if path is not None else sys.stdin.read()
    if not raw.strip():
        raise ValueError("실행 요청 JSON이 비어 있습니다")
    return json.loads(raw)


def _write_json(value: Any, stream) -> None:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    registry = ModuleRegistry(
        AnswerCacheRepository(CACHE_DIR / "answers.json")
    )
    try:
        if args.contract:
            _write_json(registry.definition(args.module_type), sys.stdout)
            return 0

        request = ModuleExecutionRequestDTO.model_validate(
            _read_request(args.request)
        )
        output = registry.execute(
            args.module_type,
            request.input,
            request.config,
        )
        _write_json(output, sys.stdout)
        return 0
    except (KeyError, OSError, ValueError, ValidationError, ModuleExecutionError) as error:
        detail = (
            error.errors(include_url=False)
            if isinstance(error, ValidationError)
            else str(error)
        )
        _write_json(
            {"error": type(error).__name__, "detail": detail},
            sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
