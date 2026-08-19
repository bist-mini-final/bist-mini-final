# Sheet Metadata Persistence

> Module type: `sheet_metadata_persistence` · Category: `Storage / DB` · Version: `2`

pgvector 적재 후 워크북 시트 크기와 감지 테이블을 DB에 저장합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `structure_input`, `index_input`
- Output ports: `output`
- Cacheable: `false`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `structure_input` | `SpreadsheetStructureOutput \| WorkbookSelectionDTO` | yes | - | 구조 감지 결과 또는 전수 직렬화용 워크북 선택 결과 |
| `index_input` | `VectorIndexDTO` | yes | - | source_files 저장이 완료된 pgvector 인덱스 결과 |

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `sheets_saved` | `integer` | yes | - | DB에 저장된 시트 수 |
| `sheet_details` | `array<object>` | no | - | - |

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

### `SpreadsheetStructureOutput`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `sheet_names` | `array<string>` | no | - | 구조 분석 대상으로 선택된 표시 시트명 |
| `tables` | `array<ClassifiedTableDTO>` | yes | - | - |
| `failed_sheets` | `array<object<string, string>>` | no | - | 분석하지 못한 시트명과 실패 사유 |

### `VectorIndexDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `index_id` | `string` | yes | - | 영속 벡터 인덱스의 콘텐츠 주소 |
| `file_name` | `string` | yes | - | 인덱싱한 원본 Excel 파일명 |
| `workbook_hash` | `string` | yes | - | 인덱싱한 Excel 파일 해시 |
| `model` | `string` | yes | - | 문서 임베딩 모델 ID |
| `dimension` | `integer` | yes | - | 벡터 차원 |
| `document_count` | `integer` | yes | - | 저장된 검색 문서 개수 |

### `WorkbookSelectionDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | 선택된 processed Excel 파일명 |
| `workbook_hash` | `string` | yes | - | 파일 변경을 식별하는 SHA-256 |
| `sheet_names` | `array<string>` | yes | - | 내부·빈 시트를 제외한 처리 대상 시트명 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "structure_input": {
      "replace_with": "SpreadsheetStructureOutput"
    },
    "index_input": {
      "replace_with": "VectorIndexDTO"
    }
  },
  "config": {}
}
```

```bash
python -m backend.tools.run_module sheet_metadata_persistence --contract
python -m backend.tools.run_module sheet_metadata_persistence --request request.json
```

HTTP에서는 `POST /api/modules/sheet_metadata_persistence/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
