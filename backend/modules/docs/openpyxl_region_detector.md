# OpenPyXL Table Region Classifier

> Module type: `openpyxl_region_detector` · Category: `Logic` · Version: `3`

Docling 테이블 경계 안에서 헤더와 데이터 영역을 셀 서식으로 분류합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `input`
- Output ports: `output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `tables` | `array<DoclingTableRegionDTO>` | yes | - | - |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `header_scan_rows` | `integer` | no | `10` | 각 테이블 상단에서 헤더 스타일을 검사할 최대 행 수 |
| `bold_ratio_threshold` | `number` | no | `0.3` | column_header로 판정할 최소 bold 셀 비율 |
| `fill_ratio_threshold` | `number` | no | `0.4` | column_header로 판정할 최소 배경색 셀 비율 |

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

### `DoclingTableRegionDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `sheet_name` | `string` | yes | - | - |
| `table_index` | `integer` | yes | - | - |
| `excel_range` | `string` | yes | - | - |
| `bbox_px` | `array<any>` | yes | - | - |
| `cell_bounds` | `TableCellBoundsDTO` | yes | - | - |

### `TableCellBoundsDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `min_row` | `integer` | yes | - | - |
| `max_row` | `integer` | yes | - | - |
| `min_column` | `integer` | yes | - | - |
| `max_column` | `integer` | yes | - | - |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "file_name": "example.xlsx",
    "workbook_hash": "<workbook_hash>",
    "tables": []
  },
  "config": {
    "header_scan_rows": 10,
    "bold_ratio_threshold": 0.3,
    "fill_ratio_threshold": 0.4
  }
}
```

```bash
python -m backend.tools.run_module openpyxl_region_detector --contract
python -m backend.tools.run_module openpyxl_region_detector --request request.json
```

HTTP에서는 `POST /api/modules/openpyxl_region_detector/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
