# Semantic Query Matcher

> Module type: `semantic_query_matcher` · Category: `Logic` · Version: `1`

예시 질의 임베딩으로 대상 시트를 판별하고, 불확실하면 전체 검색을 유지합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `query_context`
- Output ports: `semantic_match`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | - |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"text-embedding-3-small"` | - |
| `threshold` | `number` | no | `0.74` | - |
| `top_k` | `integer` | no | `5` | - |
| `vote_margin` | `number` | no | `0.05` | - |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `semantic_match` | `SemanticQueryMatchOutput` | yes | - | - |

## Referenced DTOs

### `QueryContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `question_id` | `string` | yes | - | 전체 질의 파이프라인에서 유지되는 원본 질문 ID |
| `question_text` | `string` | yes | - | 검색·컨텍스트·답변이 참조하는 사용자의 원문 질문 |

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
    "query_context": {
      "question_id": "QUERY-EXAMPLE",
      "question_text": "사용자 질문"
    }
  },
  "config": {
    "model": "text-embedding-3-small",
    "threshold": 0.74,
    "top_k": 5,
    "vote_margin": 0.05
  }
}
```

```bash
python -m backend.tools.run_module semantic_query_matcher --contract
python -m backend.tools.run_module semantic_query_matcher --request request.json
```

HTTP에서는 `POST /api/modules/semantic_query_matcher/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
