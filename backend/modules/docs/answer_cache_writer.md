# Answer Cache Writer

> Module type: `answer_cache_writer` · Category: `Output` · Version: `2`

Reader 답변에 포함된 Query Context를 기준으로 답변 캐시에 저장합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `answer_json`
- Output ports: `answer_json`
- Cacheable: `false`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `answer_json` | `AnswerDTO` | yes | - | 원 질문과 문서 계보를 포함하는 Reader 최종 답변 |

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `answer_json` | `AnswerDTO` | yes | - | 최종 답변 출력 포트 |

## Referenced DTOs

### `AnswerDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 답변이 대응하는 원본 질문 컨텍스트 |
| `document_context` | `DocumentContextDTO` | yes | - | 답변 근거가 추출된 원본 문서 컨텍스트 |
| `model` | `string` | yes | - | 답변 생성에 사용된 모델 ID |
| `answer` | `string` | yes | - | 근거 컨텍스트 기반 최종 답변 |
| `api_usage` | `ApiUsageDTO` | yes | - | LLM 토큰 사용량 |
| `latency_seconds` | `number` | yes | - | Reader 실행 시간(초) |
| `estimated_cost_usd` | `number` | yes | - | 예상 API 비용(USD) |

### `ApiUsageDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `prompt_tokens` | `integer | null` | no | `null` | 입력 토큰 수 |
| `completion_tokens` | `integer | null` | no | `null` | 출력 토큰 수 |
| `cached_tokens` | `integer | null` | no | `null` | 캐시 적중 토큰 수 |
| `reasoning_tokens` | `integer | null` | no | `null` | 추론 토큰 수 |
| `total_tokens` | `integer | null` | no | `null` | 전체 토큰 수 |

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

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "answer_json": {
      "replace_with": "AnswerDTO"
    }
  },
  "config": {}
}
```

```bash
python -m backend.tools.run_module answer_cache_writer --contract
python -m backend.tools.run_module answer_cache_writer --request request.json
```

HTTP에서는 `POST /api/modules/answer_cache_writer/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
