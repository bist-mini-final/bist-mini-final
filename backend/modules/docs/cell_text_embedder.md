# Cell Text Embedder

> Module type: `cell_text_embedder` · Category: `Logic` · Version: `3`

직렬화된 Excel 셀 문서를 배치 임베딩하고 원본 메타데이터와 함께 반환합니다.

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
| `items` | `array<CellTextDocumentDTO>` | yes | - | - |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"BAAI/bge-large-en-v1.5"` | Excel 셀 문서 임베딩에 사용할 Hugging Face 또는 OpenAI 모델 ID |
| `batch_size` | `integer` | no | `2048` | Excel 셀 문서를 한 번에 임베딩할 배치 크기 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `model` | `string` | yes | - | 문서 임베딩에 사용된 모델 ID |
| `artifact_id` | `string` | yes | - | float32 문서 벡터 아티팩트의 콘텐츠 주소 |
| `dimension` | `integer` | yes | - | 각 문서 임베딩 벡터 차원 |
| `items` | `array<EmbeddedCellTextDocumentDTO>` | yes | - | - |

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

### `EmbeddedCellTextDocumentDTO`

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
| `embedding_index` | `integer` | yes | - | 외부 임베딩 아티팩트에서 이 셀 문서 벡터의 행 번호 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "file_name": "example.xlsx",
    "workbook_hash": "<workbook_hash>",
    "items": []
  },
  "config": {
    "model": "BAAI/bge-large-en-v1.5",
    "batch_size": 2048
  }
}
```

```bash
python -m backend.tools.run_module cell_text_embedder --contract
python -m backend.tools.run_module cell_text_embedder --request request.json
```

HTTP에서는 `POST /api/modules/cell_text_embedder/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
