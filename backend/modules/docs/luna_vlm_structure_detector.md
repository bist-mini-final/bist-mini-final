# Luna Full-Sheet Structure Detector

> Module type: `luna_vlm_structure_detector` · Category: `Logic` · Version: `4`

후보 영역이나 타일 분할 없이 표시된 시트 전체 이미지와 좌표 컨텍스트를 한 번에 분석합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `input`
- Output ports: `output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | 선택된 processed Excel 파일명 |
| `workbook_hash` | `string` | yes | - | 파일 변경을 식별하는 SHA-256 |
| `sheet_names` | `array<string>` | yes | - | 내부·빈 시트를 제외한 처리 대상 시트명 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"gpt-5.6-luna"` | OpenAI Responses API 멀티모달 모델 ID |
| `max_rows` | `integer` | no | `400` | 시트에서 분석할 최대 행 수 |
| `max_columns` | `integer` | no | `60` | 시트에서 분석할 최대 열 수 |
| `max_context_cells` | `integer` | no | `50000` | 한 시트에서 좌표 컨텍스트로 전달할 최대 값 셀 수 |
| `reasoning_effort` | `string` | no | `"low"` | Luna 추론 강도 |
| `max_output_tokens` | `integer` | no | `6000` | 시트별 최대 출력 토큰 |
| `timeout_seconds` | `integer` | no | `240` | 시트별 API 요청 제한 시간(초) |
| `validation_retries` | `integer` | no | `1` | 좌표 규칙 위반 응답의 교정 재시도 횟수 |
| `system_prompt` | `string` | no | `<long default; see contract>` | 전체 시트 구조 식별 시스템 프롬프트 |
| `user_prompt_template` | `string` | no | `<long default; see contract>` | sheet_name, sheet_range, sheet_context 변수를 지원하는 전체 시트 프롬프트 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `tables` | `array<ClassifiedTableDTO>` | yes | - | - |

## Referenced DTOs

### `ClassifiedRegionDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `region_id` | `string` | yes | - | - |
| `type` | `string` | yes | - | - |
| `excel_range` | `string` | yes | - | - |
| `bbox_px` | `array<any>` | yes | - | - |
| `rows` | `array<any>` | yes | - | - |
| `columns` | `array<any>` | yes | - | - |
| `parent_ids` | `array<string>` | yes | - | - |

### `ClassifiedTableDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `sheet_name` | `string` | yes | - | - |
| `table_index` | `integer` | yes | - | - |
| `excel_range` | `string` | yes | - | - |
| `regions` | `array<ClassifiedRegionDTO>` | yes | - | - |
| `header_tree` | `array<ColumnHeaderNodeDTO>` | no | - | - |

### `ColumnHeaderNodeDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `name` | `string` | yes | - | - |
| `col_start` | `integer` | yes | - | - |
| `col_end` | `integer` | yes | - | - |
| `row_start` | `integer` | yes | - | - |
| `row_end` | `integer` | yes | - | - |
| `children` | `array<ColumnHeaderNodeDTO>` | no | - | - |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "file_name": "example.xlsx",
    "workbook_hash": "<workbook_hash>",
    "sheet_names": []
  },
  "config": {
    "model": "gpt-5.6-luna",
    "max_rows": 400,
    "max_columns": 60,
    "max_context_cells": 50000,
    "reasoning_effort": "low",
    "max_output_tokens": 6000,
    "timeout_seconds": 240,
    "validation_retries": 1,
    "system_prompt": "<use system_prompt default from ConfigDTO>",
    "user_prompt_template": "<use user_prompt_template default from ConfigDTO>"
  }
}
```

```bash
python -m backend.tools.run_module luna_vlm_structure_detector --contract
python -m backend.tools.run_module luna_vlm_structure_detector --request request.json
```

HTTP에서는 `POST /api/modules/luna_vlm_structure_detector/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
