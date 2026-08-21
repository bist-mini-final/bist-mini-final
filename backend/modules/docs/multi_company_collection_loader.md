# Multi-Company Collection Loader

> Module type: `multi_company_collection_loader` · Category: `Storage` · Version: `1`

질문 내 기업명을 정규화하여 복수 기업의 pgvector 셀 문서를 병렬 로드하고 통합합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `query_context`
- Output ports: `document_output`, `index_output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO \| null` | no | `null` | 기업명 자동 추출에 사용할 질의 계보 DTO |
| `collection_names` | `array<string> \| null` | no | `null` | 직접 지정할 pgvector 컬렉션 ID 목록 (선택 사항) |
| `target_companies` | `array<string> \| null` | no | `null` | 직접 지정할 대상 기업명 목록 (선택 사항) |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `auto_resolve_from_query` | `boolean` | no | `true` | 질문 본문에서 기업명을 자동으로 감지하여 컬렉션을 선택할지 여부 |
| `fallback_company` | `string` | no | `"IBM"` | 기업명을 감지하지 못했을 때 사용할 기본 기업명 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `document_output` | `CellTextSerializerOutput` | yes | - | - |
| `index_output` | `object` | yes | - | - |
| `loaded_collections` | `array<string>` | yes | - | - |
| `loaded_companies` | `array<string>` | yes | - | - |

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

### `CellTextSerializerOutput`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `items` | `array<CellTextDocumentDTO>` | yes | - | - |

### `QueryContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `question_id` | `string` | yes | - | 전체 질의 파이프라인에서 유지되는 원본 질문 ID |
| `question_text` | `string` | yes | - | 검색·컨텍스트·답변이 참조하는 사용자의 원문 질문 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {},
  "config": {
    "auto_resolve_from_query": true,
    "fallback_company": "IBM"
  }
}
```

```bash
python -m backend.tools.run_module multi_company_collection_loader --contract
python -m backend.tools.run_module multi_company_collection_loader --request request.json
```

HTTP에서는 `POST /api/modules/multi_company_collection_loader/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
