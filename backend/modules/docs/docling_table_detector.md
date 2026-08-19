# Docling Table Region Detector

> Module type: `docling_table_detector` · Category: `Logic` · Version: `4`

Excel 시트를 PNG로 렌더링하고 Docling으로 테이블 경계를 추출합니다.

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
| `max_rows` | `integer` | no | `400` | 시트 이미지화 및 탐지에 포함할 최대 행 수 |
| `max_columns` | `integer` | no | `60` | 시트 이미지화 및 탐지에 포함할 최대 열 수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `sheet_names` | `array<string>` | yes | - | - |
| `tables` | `array<DoclingTableRegionDTO>` | yes | - | - |

## Referenced DTOs

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
    "sheet_names": []
  },
  "config": {
    "max_rows": 400,
    "max_columns": 60
  }
}
```

```bash
python -m backend.tools.run_module docling_table_detector --contract
python -m backend.tools.run_module docling_table_detector --request request.json
```

HTTP에서는 `POST /api/modules/docling_table_detector/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
