# Structured Cell Text Serializer

> Module type: `cell_text_serializer` · Category: `Transform` · Version: `structured-cell-v5-visible-only`

분류된 Excel 셀을 Sheet·Row Header·Column Header·Cell Value 포맷으로 직렬화합니다.

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
| `tables` | `array<ClassifiedTableDTO>` | yes | - | - |

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `items` | `array<CellTextDocumentDTO>` | yes | - | - |

## Referenced DTOs

### `CellTextDocumentDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `cell_id` | `string` | yes | - | 시트 코드와 셀 좌표로 만든 검색 문서 ID |
| `sheet_name` | `string` | yes | - | 정규화된 원본 시트 이름 |
| `cell_coord` | `string` | yes | - | Excel 셀 좌표 |
| `row_header` | `array<string>` | yes | - | 상위 수준부터 수집한 행 헤더 |
| `column_header` | `array<string>` | yes | - | 상위 수준부터 수집한 열 헤더 |
| `cell_value` | `string` | yes | - | Excel 데이터 셀의 표시 값 |
| `variant` | `string` | yes | - | - |
| `text` | `string` | yes | - | 4필드 공통 포맷으로 직렬화한 검색 문서 |

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
    "tables": []
  },
  "config": {}
}
```

```bash
python -m backend.tools.run_module cell_text_serializer --contract
python -m backend.tools.run_module cell_text_serializer --request request.json
```

HTTP에서는 `POST /api/modules/cell_text_serializer/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
