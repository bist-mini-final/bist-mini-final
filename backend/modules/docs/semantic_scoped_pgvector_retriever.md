# Semantic-Scoped pgvector Retriever

> Module type: `semantic_scoped_pgvector_retriever` · Category: `Logic` · Version: `1`

정답셋 기반 분해 계획과 충분한 신뢰도가 있을 때만 pgvector를 시트 범위로 검색하고, 결과가 없거나 불확실하면 전체 컬렉션을 검색합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `query_input`, `index_input`, `semantic_match`
- Output ports: `dense_result`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_input` | `EmbeddingsDTO` | yes | - | - |
| `index_input` | `IndexOutputDTO` | yes | - | - |
| `semantic_match` | `SemanticQueryMatchOutput` | yes | - | - |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `top_k` | `integer` | no | `1000` | - |
| `min_scope_confidence` | `number` | no | `0.8` | - |

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

### `RouterMetricsDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `kind` | `string` | yes | - | - |
| `model` | `string` | yes | - | - |
| `latency_seconds` | `number` | yes | - | - |
| `api_usage` | `object<string, integer>` | no | - | - |
| `estimated_cost_usd` | `number` | no | `0` | - |

### `SemanticMatchItemDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `example_id` | `string` | yes | - | - |
| `question` | `string` | yes | - | - |
| `target` | `string` | yes | - | - |
| `sheets` | `array<string>` | yes | - | - |
| `similarity` | `number` | yes | - | - |

### `SemanticQueryMatchOutput`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `matched` | `boolean` | yes | - | - |
| `target` | `string \| null` | yes | - | - |
| `confidence` | `number` | yes | - | - |
| `sheets` | `array<string>` | yes | - | - |
| `reason` | `string` | yes | - | - |
| `matches` | `array<SemanticMatchItemDTO>` | yes | - | - |
| `query_type` | `integer \| null` | no | `null` | - |
| `subqueries` | `array<string>` | no | - | - |
| `metrics` | `RouterMetricsDTO` | no | - | - |

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
    },
    "semantic_match": {
      "replace_with": "SemanticQueryMatchOutput"
    }
  },
  "config": {
    "top_k": 1000,
    "min_scope_confidence": 0.8
  }
}
```

```bash
python -m backend.tools.run_module semantic_scoped_pgvector_retriever --contract
python -m backend.tools.run_module semantic_scoped_pgvector_retriever --request request.json
```

HTTP에서는 `POST /api/modules/semantic_scoped_pgvector_retriever/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
