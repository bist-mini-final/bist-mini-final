# LLM Reader Answer

> Module type: `reader` · Category: `Output` · Version: `3`

질문·문서 계보가 포함된 확장 Excel 컨텍스트로 실제 LLM 답변을 생성합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `context_json`
- Output ports: `answer_json`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `context_json` | `ContextDTO` | yes | - | 원 질문과 원본 문서 식별자를 포함하는 Context Expander의 grounded context |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"gpt-5.6-luna"` | 답변 생성에 사용할 LLM ID |
| `preset` | `string` | no | `"luna_reader"` | Reader 프롬프트 프리셋 ID |
| `system_prompt` | `string` | no | `<long default; see contract>` | 근거 기반 답변 규칙을 정의하는 시스템 프롬프트 |
| `user_prompt_template` | `string` | no | `"Retrieved Financial Cell Context:\n{context_text}\n\nUser Question:\n{question}\n\nGrounded Financial Answer:"` | {context_text}, {question} 변수를 지원하는 사용자 템플릿 |

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

### `ContextDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | Reader까지 보존되는 원본 질문 컨텍스트 |
| `document_context` | `DocumentContextDTO` | yes | - | 컨텍스트 블록이 추출된 원본 문서 컨텍스트 |
| `top_k_used` | `integer` | yes | - | 확장에 실제 사용한 RRF 후보 수 |
| `adjacent_radius` | `integer` | yes | - | 검색 셀 기준 인접 행 확장 반경 |
| `context_characters` | `integer` | yes | - | 전체 컨텍스트 문자 수 |
| `context_blocks` | `array<string>` | yes | - | Reader가 그대로 사용할 시트·행 단위 실제 셀 컨텍스트 |
| `block_count` | `integer` | yes | - | 생성된 확장 행 블록 개수 |

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
    "context_json": {
      "replace_with": "ContextDTO"
    }
  },
  "config": {
    "model": "gpt-5.6-luna",
    "preset": "luna_reader",
    "system_prompt": "<use system_prompt default from ConfigDTO>",
    "user_prompt_template": "Retrieved Financial Cell Context:\n{context_text}\n\nUser Question:\n{question}\n\nGrounded Financial Answer:"
  }
}
```

```bash
python -m backend.tools.run_module reader --contract
python -m backend.tools.run_module reader --request request.json
```

HTTP에서는 `POST /api/modules/reader/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
