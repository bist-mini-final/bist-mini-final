# Time-Series Full-Row Context Expander

> Module type: `timeseries_context_expander` · Category: `Logic` · Version: `1`

검색된 셀의 행(Row)을 감지하여 전체 연도 컬럼을 연속 시계열 테이블로 자동 확장합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `retrieval_json`, `document_input`
- Output ports: `context_json`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `retrieval_json` | `RetrievalDTO` | yes | - | RRF 융합 검색 결과 DTO |
| `document_input` | `CellTextSerializerOutput` | yes | - | Excel 구조화 셀 문서 입력 포트 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `top_k` | `integer` | no | `100` | 확장할 상위 RRF 후보 수 |
| `expand_full_row` | `boolean` | no | `true` | Row Header 매칭 시 해당 행의 전체 연도 컬럼 셀을 연속 시계열로 확장할지 여부 |
| `adjacent_radius` | `integer` | no | `2` | 인접 행 추가 확장 반경 |
| `max_blocks` | `integer` | no | `500` | 생성할 최대 컨텍스트 블록 수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | Reader까지 보존되는 원본 질문 컨텍스트 |
| `document_context` | `DocumentContextDTO` | yes | - | 컨텍스트 블록이 추출된 원본 문서 컨텍스트 |
| `top_k_used` | `integer` | yes | - | 확장에 실제 사용한 RRF 후보 수 |
| `adjacent_radius` | `integer` | yes | - | 검색 셀 기준 인접 행 확장 반경 |
| `context_characters` | `integer` | yes | - | 전체 컨텍스트 문자 수 |
| `context_blocks` | `array<string>` | yes | - | Reader가 그대로 사용할 시트·행 단위 실제 셀 컨텍스트 |
| `block_count` | `integer` | yes | - | 생성된 확장 행 블록 개수 |

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

### `DocumentContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | 검색 문서와 벡터 인덱스가 만들어진 원본 파일명 |
| `workbook_hash` | `string` | yes | - | 원본 문서 버전을 식별하는 콘텐츠 해시 |

### `QueryContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `question_id` | `string` | yes | - | 전체 질의 파이프라인에서 유지되는 원본 질문 ID |
| `question_text` | `string` | yes | - | 검색·컨텍스트·답변이 참조하는 사용자의 원문 질문 |

### `RetrievalDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 결합 검색 결과가 대응하는 원본 질문 컨텍스트 |
| `document_context` | `DocumentContextDTO` | yes | - | 결합 검색 결과가 참조하는 원본 문서 컨텍스트 |
| `items` | `array<RrfCandidateDTO>` | yes | - | RRF 점수 내림차순 결합 후보 |

### `RrfCandidateDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `rank` | `integer` | yes | - | RRF 결합 순위 |
| `cell_id` | `string` | yes | - | 검색된 셀의 고유 ID |
| `rrf_score` | `number` | yes | - | Reciprocal Rank Fusion 점수 |
| `text` | `string` | yes | - | 검색된 셀의 직렬화 텍스트 |
| `matched_subquery` | `string` | yes | - | 해당 셀과 매칭된 서브쿼리 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "retrieval_json": {
      "replace_with": "RetrievalDTO"
    },
    "document_input": {
      "replace_with": "CellTextSerializerOutput"
    }
  },
  "config": {
    "top_k": 100,
    "expand_full_row": true,
    "adjacent_radius": 2,
    "max_blocks": 500
  }
}
```

```bash
python -m backend.tools.run_module timeseries_context_expander --contract
python -m backend.tools.run_module timeseries_context_expander --request request.json
```

HTTP에서는 `POST /api/modules/timeseries_context_expander/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
