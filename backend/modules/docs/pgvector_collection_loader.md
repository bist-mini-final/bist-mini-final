# PostgreSQL pgvector Collection Loader

> Module type: `pgvector_collection_loader` · Category: `Source` · Version: `1`

PostgreSQL 16 pgvector DB에 적재된 다중 벡터 컬렉션을 로드하여 통합 document_output과 index_output을 파이프라인에 공급합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: 없음(Source)
- Output ports: `document_output`, `index_output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `collection_name` | `string \| null` | no | `"SPG_Company_KeyStats_v4.xlsm"` | 단일 컬렉션 선택 시 컬렉션 이름 또는 파일명 |
| `collection_names` | `array<string>` | no | - | 다중 선택 시 로드할 PostgreSQL pgvector 컬렉션 ID 또는 파일명 목록 |

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `document_output` | `DocumentOutputDTO` | yes | - | - |
| `index_output` | `IndexOutputDTO` | yes | - | - |

## Referenced DTOs

### `DocumentOutputDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `items` | `array<object>` | yes | - | - |

### `IndexOutputDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `index_id` | `string` | yes | - | - |
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `model` | `string` | yes | - | - |
| `dimension` | `integer` | yes | - | - |
| `document_count` | `integer` | yes | - | - |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {},
  "config": {}
}
```

```bash
python -m backend.tools.run_module pgvector_collection_loader --contract
python -m backend.tools.run_module pgvector_collection_loader --request request.json
```

HTTP에서는 `POST /api/modules/pgvector_collection_loader/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
