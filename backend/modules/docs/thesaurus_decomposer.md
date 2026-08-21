# Thesaurus Financial Decomposer

> Module type: `thesaurus_decomposer` · Category: `Logic` · Version: `1`

재무 지표 사전(Thesaurus)을 참조하여 질문을 정밀한 표준 서브쿼리로 분해합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `query_context`
- Output ports: `subqueries`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 질문 메타데이터 및 질문 본문을 포함하는 계보 DTO |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"gpt-5.6-luna"` | 서브쿼리 분해에 사용할 LLM 모델 ID |
| `preset` | `string` | no | `"luna_thesaurus_decomposer"` | Decomposer 프롬프트 프리셋 ID |
| `system_prompt` | `string` | no | `<long default; see contract>` | 표준 시소러스 가이드가 포함된 시스템 프롬프트 |
| `user_prompt_template` | `string` | no | `"Korean Query: \"{question}\"\nJSON Output:"` | {question} 템플릿 변수를 포함하는 사용자 프롬프트 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 서브쿼리가 파생된 원본 질문 컨텍스트 |
| `subqueries` | `array<string>` | yes | - | 4필드 포맷으로 정규화·확장된 최종 검색 서브쿼리 |

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
    }
  },
  "config": {
    "model": "gpt-5.6-luna",
    "preset": "luna_thesaurus_decomposer",
    "system_prompt": "<use system_prompt default from ConfigDTO>",
    "user_prompt_template": "Korean Query: \"{question}\"\nJSON Output:"
  }
}
```

```bash
python -m backend.tools.run_module thesaurus_decomposer --contract
python -m backend.tools.run_module thesaurus_decomposer --request request.json
```

HTTP에서는 `POST /api/modules/thesaurus_decomposer/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
