# Local VLM Table Structure Detector

> Module type: `local_vlm_structure_detector` · Category: `Logic` · Version: `5`

셀 타입 오버레이 이미지와 좌표·타입·값 컨텍스트를 로컬 VLM에 함께 전달해 표와 계층 헤더 영역을 식별합니다.

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
| `model` | `string` | no | `"qwen3-vl:4b-instruct"` | Ollama에 설치된 로컬 멀티모달 모델 ID |
| `max_rows` | `integer` | no | `400` | 시트에서 분석할 최대 행 수 |
| `max_columns` | `integer` | no | `60` | 시트에서 분석할 최대 열 수 |
| `max_context_cells` | `integer` | no | `15000` | 한 시트 요청에 포함할 최대 값 셀 수(초과 시 생략하지 않고 실패) |
| `context_window` | `integer` | no | `65536` | Ollama 추론 컨텍스트 길이 |
| `timeout_seconds` | `integer` | no | `900` | 시트별 로컬 VLM 요청 제한 시간(초) |
| `validation_retries` | `integer` | no | `1` | 좌표 규칙을 위반한 로컬 VLM 응답의 교정 재시도 횟수 |
| `system_prompt` | `string` | no | `<long default; see contract>` | 시트 구조 식별 시스템 프롬프트 |
| `user_prompt_template` | `string` | no | `<long default; see contract>` | {sheet_name}, {sheet_context} 변수를 지원하는 사용자 프롬프트 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `sheet_names` | `array<string>` | no | - | 구조 분석 대상으로 선택된 표시 시트명 |
| `tables` | `array<ClassifiedTableDTO>` | yes | - | - |
| `failed_sheets` | `array<object<string, string>>` | no | - | 분석하지 못한 시트명과 실패 사유 |

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
    "model": "qwen3-vl:4b-instruct",
    "max_rows": 400,
    "max_columns": 60,
    "max_context_cells": 15000,
    "context_window": 65536,
    "timeout_seconds": 900,
    "validation_retries": 1,
    "system_prompt": "<use system_prompt default from ConfigDTO>",
    "user_prompt_template": "Analyze sheet {sheet_name}.\nThe compact tuple format is [excel_coord, value_type, value, optional_flags].\nHere is the exact coordinate context:\n{sheet_context}"
  }
}
```

```bash
python -m backend.tools.run_module local_vlm_structure_detector --contract
python -m backend.tools.run_module local_vlm_structure_detector --request request.json
```

HTTP에서는 `POST /api/modules/local_vlm_structure_detector/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
