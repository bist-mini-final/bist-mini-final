# BFS + LLM Table Structure Detector

> Module type: `bfs_llm_structure_detector` · Category: `Logic` · Version: `5`

셀 연결요소로 표를 분리하고 상단 행만 LLM으로 판단해 제목·계층 헤더·데이터 영역을 구성합니다.

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
| `model` | `string` | no | `"gpt-5.6-luna"` | 표 경계 판단에 사용할 LLM ID |
| `max_rows` | `integer` | no | `400` | 시트에서 분석할 최대 행 수 |
| `max_columns` | `integer` | no | `60` | 시트에서 분석할 최대 열 수 |
| `merge_gap` | `integer` | no | `2` | BFS 영역을 병합할 빈 셀 간격 |
| `min_non_empty_cells` | `integer` | no | `2` | 표 후보로 유지할 최소 비어 있지 않은 셀 수 |
| `min_table_columns` | `integer` | no | `2` | 직렬화 대상 표 후보의 최소 열 수 |
| `header_candidate_rows` | `integer` | no | `10` | LLM 경계 판정에 전달할 표 상단 행 수 |
| `llm_batch_size` | `integer` | no | `8` | 한 LLM 요청에서 함께 판정할 표 후보 수 |
| `system_prompt` | `string` | no | `<long default; see contract>` | 제목·헤더·데이터 경계 판단 지시 |
| `user_prompt_template` | `string` | no | `<long default; see contract>` | {regions_json} 변수를 지원하는 사용자 프롬프트 |

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
    "model": "gpt-5.6-luna",
    "max_rows": 400,
    "max_columns": 60,
    "merge_gap": 2,
    "min_non_empty_cells": 2,
    "min_table_columns": 2,
    "header_candidate_rows": 10,
    "llm_batch_size": 8,
    "system_prompt": "<use system_prompt default from ConfigDTO>",
    "user_prompt_template": "Analyze the following BFS-detected Excel table regions. Empty/error cells are represented as null. Merged-cell coordinates are marked explicitly.\n{regions_json}"
  }
}
```

```bash
python -m backend.tools.run_module bfs_llm_structure_detector --contract
python -m backend.tools.run_module bfs_llm_structure_detector --request request.json
```

HTTP에서는 `POST /api/modules/bfs_llm_structure_detector/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
