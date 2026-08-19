# Exhaustive Cell Header Serializer

> Module type: `exhaustive_cell_text_serializer` · Category: `Transform` · Version: `exhaustive-cell-v1-visible-only`

모든 표시 값 셀을 데이터 셀로 보고 왼쪽 행 후보와 위쪽 열 후보의 전체 조합을 결정적으로 직렬화합니다.

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
| `variant_mode` | `string` | no | `"header_only"` | 각 헤더 조합에서 생성할 검색 문서 형태. header_only는 Cell Value를 ?로 두고, header_with_value는 실제 셀 값을 포함합니다 |
| `deduplicate_header_values` | `boolean` | no | `true` | 같은 방향에서 값이 동일한 여러 셀은 같은 직렬화 문장을 만들므로 한 후보로 합칩니다. 끄면 셀 좌표별 조합을 모두 생성합니다 |
| `max_documents` | `integer` | no | `250000` | 조합 폭증으로 프로세스가 종료되는 것을 막는 안전 한도. 초과 시 일부만 저장하지 않고 실행 전체를 실패시킵니다 |

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
    "variant_mode": "header_only",
    "deduplicate_header_values": true,
    "max_documents": 250000
  }
}
```

```bash
python -m backend.tools.run_module exhaustive_cell_text_serializer --contract
python -m backend.tools.run_module exhaustive_cell_text_serializer --request request.json
```

HTTP에서는 `POST /api/modules/exhaustive_cell_text_serializer/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
