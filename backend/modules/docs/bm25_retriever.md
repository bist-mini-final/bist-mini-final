# BM25 Keyword Retriever

> Module type: `bm25_retriever` · Category: `Logic` · Version: `4`

서브쿼리와 Excel 셀 문서를 받아 Okapi BM25 순위를 계산합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `query_input`, `document_input`
- Output ports: `bm25_result`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_input` | `SubqueriesDTO` | yes | - | 질문 측 서브쿼리 입력 포트 |
| `document_input` | `CellTextSerializerOutput` | yes | - | Excel 측 구조화 셀 문서 입력 포트 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `k1` | `number` | no | `1.5` | Okapi BM25 term-frequency saturation 상수 |
| `b` | `number` | no | `0.75` | Okapi BM25 문서 길이 정규화 상수 |
| `top_k` | `integer` | no | `1000` | 각 서브쿼리별 BM25 후보 최대 개수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 검색 후보가 대응하는 원본 질문 컨텍스트 |
| `document_context` | `DocumentContextDTO` | yes | - | 검색 후보가 추출된 원본 문서 컨텍스트 |
| `items` | `array<RankedSearchCandidateDTO>` | yes | - | 각 matched_subquery 내부 검색 점수 내림차순 후보 목록 |

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

### `RankedSearchCandidateDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `rank` | `integer` | yes | - | 검색기 내부 후보 순위 |
| `cell_id` | `string` | yes | - | 검색된 셀의 고유 ID |
| `score` | `number` | yes | - | 해당 검색기가 계산한 원본 점수 |
| `text` | `string` | yes | - | 검색된 셀의 직렬화 텍스트 |
| `matched_subquery` | `string` | yes | - | 해당 셀과 매칭된 서브쿼리 |

### `SubqueriesDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 서브쿼리가 파생된 원본 질문 컨텍스트 |
| `subqueries` | `array<string>` | yes | - | 4필드 포맷으로 정규화·확장된 최종 검색 서브쿼리 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "query_input": {
      "replace_with": "SubqueriesDTO"
    },
    "document_input": {
      "replace_with": "CellTextSerializerOutput"
    }
  },
  "config": {
    "k1": 1.5,
    "b": 0.75,
    "top_k": 1000
  }
}
```

```bash
python -m backend.tools.run_module bm25_retriever --contract
python -m backend.tools.run_module bm25_retriever --request request.json
```

HTTP에서는 `POST /api/modules/bm25_retriever/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
