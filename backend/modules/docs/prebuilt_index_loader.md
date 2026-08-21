# Pre-built Vector Index Loader

> Module type: `prebuilt_index_loader` · Category: `Source` · Version: `2`

공유된 사전 인덱싱 단일 파일(.parquet / .json)을 로드하여 document_output과 index_output을 즉시 생성합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: 없음(Source)
- Output ports: `document_output`, `index_output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | no | `"SPG_Company_KeyStats_v3_prebuilt.parquet"` | data/source_files 또는 data/vector_db에 공유된 사전 구축 인덱스 (.parquet / .json) 파일명 |

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
python -m backend.tools.run_module prebuilt_index_loader --contract
python -m backend.tools.run_module prebuilt_index_loader --request request.json
```

HTTP에서는 `POST /api/modules/prebuilt_index_loader/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
