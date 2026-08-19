# PostgreSQL pgvector Writer

> Module type: `pgvector_index_writer` · Category: `Transform` · Version: `1`

셀 임베딩과 청크 메타데이터를 PostgreSQL 16 pgvector DB의 6개 ERD 테이블 및 HNSW 인덱스에 영구 적재합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `input`
- Output ports: `index_output`
- Cacheable: `false`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `model` | `string` | yes | - | 문서 임베딩에 사용된 모델 ID |
| `artifact_id` | `string` | yes | - | float32 문서 벡터 아티팩트의 콘텐츠 주소 |
| `dimension` | `integer` | yes | - | 각 문서 임베딩 벡터 차원 |
| `items` | `array<EmbeddedCellTextDocumentDTO>` | yes | - | - |
| `duration_seconds` | `number \| null` | no | `null` | - |
| `total_tokens` | `integer \| null` | no | `null` | - |
| `estimated_cost_usd` | `number \| null` | no | `null` | - |
| `estimated_cost_krw` | `number \| null` | no | `null` | - |
| `batch_size` | `integer \| null` | no | `null` | - |

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `index_id` | `string` | yes | - | 영속 벡터 인덱스의 콘텐츠 주소 |
| `file_name` | `string` | yes | - | 인덱싱한 원본 Excel 파일명 |
| `workbook_hash` | `string` | yes | - | 인덱싱한 Excel 파일 해시 |
| `model` | `string` | yes | - | 문서 임베딩 모델 ID |
| `dimension` | `integer` | yes | - | 벡터 차원 |
| `document_count` | `integer` | yes | - | 저장된 검색 문서 개수 |

## Referenced DTOs

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
    "model": "<model>",
    "artifact_id": "<artifact_id>",
    "dimension": 1,
    "items": []
  },
  "config": {}
}
```

```bash
python -m backend.tools.run_module pgvector_index_writer --contract
python -m backend.tools.run_module pgvector_index_writer --request request.json
```

HTTP에서는 `POST /api/modules/pgvector_index_writer/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
