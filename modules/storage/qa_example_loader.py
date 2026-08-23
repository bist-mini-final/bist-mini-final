"""질의 라우팅 벤치마크 및 시연용 QA 예시 뱅크를 로드하는 소스 모듈.

`data/qa_examples/` 디렉터리의 JSON 파일 또는 내장 프리셋으로부터 사전 정의된 질문-시트 라우팅 예시 목록을 로드하여
시맨틱 매처 모듈이 참조할 수 있는 구조화된 카탈로그를 제공합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "file_name": "sample_qa_bank.json"
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "examples": [
        {
          "question": "2023년 삼성전자 영업이익은?",
          "route": "손익계산서",
          "sheet": "손익계산서",
          "description": "단일 지표 조회"
        }
      ],
      "total_count": 1
    }
    ```
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field

from backend.core.settings import PROJECT_DIR
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)

logger = logging.getLogger(__name__)

QA_EXAMPLES_DIR = PROJECT_DIR / "data" / "qa_examples"

BUILTIN_EXAMPLES = [
    {
        "question": "IBM의 LTM 기준 시가총액은?",
        "route": "KeyStats",
        "sheet": "KeyStats",
        "description": "단일 지표 조회 — 시가총액",
    },
    {
        "question": "2021~2025년 IBM 매출액 CAGR은?",
        "route": "KeyStats",
        "sheet": "KeyStats",
        "description": "기간 추세 분석 — 매출 CAGR",
    },
    {
        "question": "IBM의 자본구조(부채/현금)와 P/E 멀티플을 정리해줘",
        "route": "KeyStats",
        "sheet": "KeyStats",
        "description": "복수 지표 조회 및 비교",
    },
    {
        "question": "2025년 당기순이익 대비 영업현금흐름 비율은?",
        "route": "KeyStats",
        "sheet": "KeyStats",
        "description": "재무 계산",
    },
    {
        "question": "순이익 급감에도 영업현금흐름이 유지된 원인은?",
        "route": "KeyStats",
        "sheet": "KeyStats",
        "description": "심층 추론 / 원인 분석",
    },
    {
        "question": "최근 성장 추세 유지 시 2026년 Total Revenue는?",
        "route": "KeyStats",
        "sheet": "KeyStats",
        "description": "지표 전망 및 예측",
    },
]


class QaExampleLoaderInputDTO(ModuleInputDTO):
    file_name: Optional[str] = Field(
        default=None,
        description=(
            "data/qa_examples/ 아래의 JSON 파일명. "
            "비워두면 내장 예시 세트를 사용합니다."
        ),
    )


class QaExampleLoaderConfigDTO(ModuleConfigDTO):
    include_builtin: bool = Field(
        default=True,
        description="내장 예시 세트를 함께 포함할지 여부",
    )


class QaExampleItem(ModuleDTO):
    question: str = Field(description="예시 질문 텍스트")
    route: str = Field(description="라우팅 대상 (파일/시트/파이프라인)")
    sheet: str = Field(description="참조할 시트명")
    description: str = Field(default="", description="질문 유형 설명")


class QaExampleLoaderOutput(ModuleDTO):
    examples: List[QaExampleItem]
    total_count: int = Field(description="로드된 예시 총 개수")
    source: str = Field(description="로드 소스 ('builtin' / 파일명)")


class QaExampleLoaderModule(BaseModule):
    definition = ModuleDefinition(
        type="qa_example_loader",
        label="QA Example Bank Loader",
        category="Source",
        description=(
            "시맨틱 쿼리 매칭 라우팅에 사용할 QA 예시 뱅크를 로드합니다. "
            "질문 임베딩 유사도 검색으로 '어떤 파일/시트를 참조해야 하는가'를 결정하는 데 사용됩니다."
        ),
        inputs=[],
        outputs=["output"],
        config_fields=["include_builtin"],
        raw_output=True,
        version="2",
    )
    input_model = QaExampleLoaderInputDTO
    config_model = QaExampleLoaderConfigDTO
    output_model = QaExampleLoaderOutput

    def contract(self) -> Dict[str, Any]:
        contract = super().contract()
        # Populate enum with available JSON files
        available = self._available_files()
        file_schema = contract["input_schema"]["properties"]["file_name"]
        file_schema["enum"] = [None, *available]
        return contract

    def _available_files(self) -> List[str]:
        if not QA_EXAMPLES_DIR.is_dir():
            return []
        return sorted(p.name for p in QA_EXAMPLES_DIR.glob("*.json"))

    def execute(
        self,
        input_data: QaExampleLoaderInputDTO,
        config: Optional[QaExampleLoaderConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or QaExampleLoaderConfigDTO()
        examples: List[Dict[str, Any]] = []
        source = "builtin"

        if input_data.file_name:
            requested = Path(input_data.file_name)
            if (
                requested.name != input_data.file_name
                or requested.suffix.lower() != ".json"
            ):
                raise ModuleExecutionError("QA 예시 파일은 디렉터리 내 JSON 파일명만 허용됩니다")
            path = (QA_EXAMPLES_DIR / requested.name).resolve()
            if path.parent != QA_EXAMPLES_DIR.resolve():
                raise ModuleExecutionError("QA 예시 파일 경로가 허용된 디렉터리를 벗어났습니다")
            if not path.is_file():
                raise ModuleExecutionError(
                    f"QA 예시 파일을 찾을 수 없습니다: {input_data.file_name}"
                )
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                loaded = raw if isinstance(raw, list) else raw.get("examples", [])
                examples.extend(loaded)
                source = input_data.file_name
            except (json.JSONDecodeError, KeyError) as err:
                raise ModuleExecutionError(
                    f"QA 예시 파일 파싱 오류: {err}"
                ) from err

        if cfg.include_builtin or not input_data.file_name:
            examples.extend(BUILTIN_EXAMPLES)

        items = [
                QaExampleItem(
                    question=ex.get("question", ""),
                    route=ex.get("route", "KeyStats"),
                    sheet=ex.get("sheet", "KeyStats"),
                    description=ex.get("description", ""),
                ).model_dump()
            for ex in examples
        ]

        return {
            "examples": items,
            "total_count": len(items),
            "source": source,
        }


__all__ = [
    "BUILTIN_EXAMPLES",
    "QA_EXAMPLES_DIR",
    "QaExampleItem",
    "QaExampleLoaderConfigDTO",
    "QaExampleLoaderInputDTO",
    "QaExampleLoaderModule",
    "QaExampleLoaderOutput",
]
