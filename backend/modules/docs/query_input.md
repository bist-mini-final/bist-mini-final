# Query Input & Search

> Module type: `query_input` · Category: `Source` · Version: `2`

질문을 받아 캐시 답변 또는 질문 식별자가 포함된 Query Context를 전달합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: 없음(Source)
- Output ports: `cached_answer`, `query_context`
- Cacheable: `false`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query` | `string` | yes | - | 검색할 사용자의 자연어 질문(공백 제외 1~1000자) |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `threshold` | `number` | no | `0.65` | 캐시 질문을 일치로 판정할 최소 유사도(0~1) |

## Output DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Referenced DTOs

### `CachedAnswerDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 캐시 답변이 대응하는 질문 |
| `answer` | `string` | yes | - | 캐시에 저장된 기존 LLM 답변 |

### `CachedAnswerOutput`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `cached_answer` | `CachedAnswerDTO` | yes | - | 질문 계보가 포함된 캐시 답변 |

### `QueryContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `question_id` | `string` | yes | - | 전체 질의 파이프라인에서 유지되는 원본 질문 ID |
| `question_text` | `string` | yes | - | 검색·컨텍스트·답변이 참조하는 사용자의 원문 질문 |

### `QueryContextOutput`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 후속 질의 파이프라인 전체에 전달할 원본 질문 컨텍스트 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "query": "사용자 질문"
  },
  "config": {
    "threshold": 0.65
  }
}
```

```bash
python -m backend.tools.run_module query_input --contract
python -m backend.tools.run_module query_input --request request.json
```

HTTP에서는 `POST /api/modules/query_input/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
