# Query Embedder

> Module type: `embedder` · Category: `Logic` · Version: `7`

서브쿼리의 임베딩 실행 메타데이터를 생성합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `input`
- Output ports: `output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 서브쿼리가 파생된 원본 질문 컨텍스트 |
| `subqueries` | `array<string>` | yes | - | 4필드 포맷으로 정규화·확장된 최종 검색 서브쿼리 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"BAAI/bge-large-en-v1.5"` | 서브쿼리 임베딩에 사용할 Hugging Face 또는 OpenAI 모델 ID |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 임베딩이 파생된 원본 질문 컨텍스트 |
| `items` | `object<string, array<number>>` | yes | - | 서브쿼리를 key, L2 정규화 숫자 벡터를 value로 갖는 매핑 |

## Referenced DTOs

### `QueryContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `question_id` | `string` | yes | - | 전체 질의 파이프라인에서 유지되는 원본 질문 ID |
| `question_text` | `string` | yes | - | 검색·컨텍스트·답변이 참조하는 사용자의 원문 질문 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "query_context": {
      "question_id": "QUERY-EXAMPLE",
      "question_text": "사용자 질문"
    },
    "subqueries": []
  },
  "config": {
    "model": "BAAI/bge-large-en-v1.5"
  }
}
```

```bash
python -m backend.tools.run_module embedder --contract
python -m backend.tools.run_module embedder --request request.json
```

HTTP에서는 `POST /api/modules/embedder/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
