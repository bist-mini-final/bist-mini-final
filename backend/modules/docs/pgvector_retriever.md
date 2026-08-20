# PostgreSQL pgvector Retriever

> Module type: `pgvector_retriever` · Category: `Logic` · Version: `1`

질의 임베딩으로 PostgreSQL 16 pgvector DB의 IVFFlat 코사인 인덱스를 실시간 검색합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `query_input`, `index_input`
- Output ports: `dense_result`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_input` | `EmbeddingsDTO` | yes | - | 질문 측 서브쿼리 임베딩 입력 포트 |
| `index_input` | `IndexOutputDTO` | yes | - | pgvector Collection Loader 또는 pgvector Index Writer가 생성한 인덱스 참조 DTO |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `top_k` | `integer` | no | `100` | 각 서브쿼리별 pgvector HNSW 후보 검색 최대 개수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 검색 후보가 대응하는 원본 질문 컨텍스트 |
| `document_context` | `DocumentContextDTO` | yes | - | 검색 후보가 추출된 원본 문서 컨텍스트 |
| `items` | `array<RankedSearchCandidateDTO>` | yes | - | 각 matched_subquery 내부 검색 점수 내림차순 후보 목록 |

## Referenced DTOs

### `DocumentContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | 검색 문서와 벡터 인덱스가 만들어진 원본 파일명 |
| `workbook_hash` | `string` | yes | - | 원본 문서 버전을 식별하는 콘텐츠 해시 |

### `EmbeddingsDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 임베딩이 파생된 원본 질문 컨텍스트 |
| `items` | `object<string, array<number>>` | yes | - | 서브쿼리를 key, L2 정규화 숫자 벡터를 value로 갖는 매핑 |

### `IndexOutputDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `index_id` | `string` | yes | - | - |
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `model` | `string` | yes | - | - |
| `dimension` | `integer` | yes | - | - |
| `document_count` | `integer` | yes | - | - |

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

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "query_input": {
      "replace_with": "EmbeddingsDTO"
    },
    "index_input": {
      "replace_with": "IndexOutputDTO"
    }
  },
  "config": {
    "top_k": 100
  }
}
```

```bash
python -m backend.tools.run_module pgvector_retriever --contract
python -m backend.tools.run_module pgvector_retriever --request request.json
```

HTTP에서는 `POST /api/modules/pgvector_retriever/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
