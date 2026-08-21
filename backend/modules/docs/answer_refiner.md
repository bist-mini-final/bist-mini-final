# Direct Cell Answer Refiner

> Module type: `answer_refiner` · Category: `Output` · Version: `1`

Reader 답변에서 추가 검증이 필요한 셀을 LLM 2D 공간 위상 추론으로 선별하고, PostgreSQL pgvector 메타데이터에서 해당 셀들을 직접 조회하여 답변을 보강 및 정밀 개선합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `answer_json`
- Output ports: `refined_answer_json`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `answer_json` | `AnswerDTO` | yes | - | Reader 모듈로부터 생성된 초기 답변 및 질문·문서 계보 DTO |
| `target_cell_ids` | `array<string> \| null` | no | `null` | 직접 조회를 강제할 추가 셀 ID 목록 (선택 사항) |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"gpt-5.6-luna"` | 답변 정밀 개선에 사용할 LLM ID |
| `preset` | `string` | no | `"luna_cell_refiner"` | Refiner 프롬프트 프리셋 ID |
| `system_prompt` | `string` | no | `<long default; see contract>` | 직접 셀 근거 기반 답변 정밀 교정 시스템 프롬프트 |
| `user_prompt_template` | `string` | no | `<long default; see contract>` | {question}, {initial_answer}, {direct_cells_text} 템플릿 변수를 포함하는 사용자 프롬프트 |
| `cell_extractor_prompt` | `string` | no | `<long default; see contract>` | 2D 스프레드시트 공간 위상 추론을 통한 타겟 셀 후보 추출 시스템 프롬프트 |
| `max_direct_cells` | `integer` | no | `25` | DB에서 직접 인출할 최대 셀 개수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `refined_answer_json` | `RefinedAnswerDTO` | yes | - | 최종 개선된 답변 출력 포트 |

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
| `prompt_tokens` | `integer \| null` | no | `null` | 입력 토큰 수 |
| `completion_tokens` | `integer \| null` | no | `null` | 출력 토큰 수 |
| `cached_tokens` | `integer \| null` | no | `null` | 캐시 적중 토큰 수 |
| `reasoning_tokens` | `integer \| null` | no | `null` | 추론 토큰 수 |
| `total_tokens` | `integer \| null` | no | `null` | 전체 토큰 수 |

### `DirectCellDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `cell_id` | `string` | yes | - | 고유 셀 식별자 (예: IS:I16 또는 IS Cell I16) |
| `sheet_name` | `string` | yes | - | 시트명 (예: Income_Statement) |
| `cell_coord` | `string` | yes | - | 셀 좌표 (예: I16) |
| `cell_value` | `string \| null` | no | `null` | 원장 셀 값 |
| `row_header` | `array<string>` | no | - | 계층형 행 헤더 목록 |
| `column_header` | `array<string>` | no | - | 계층형 열 헤더 목록 |
| `company_name` | `string \| null` | no | `null` | 기업명 |
| `source_text` | `string` | yes | - | 청크 원문 텍스트 |

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

### `RefinedAnswerDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query_context` | `QueryContextDTO` | yes | - | 원본 질문 식별자 및 원문 |
| `document_context` | `DocumentContextDTO` | yes | - | 참조 원본 문서 식별자 |
| `initial_answer` | `string` | yes | - | Reader 모듈이 생성했던 1차 초기 답변 |
| `refined_answer` | `string` | yes | - | 직접 셀 메타데이터가 반영된 최종 개선 답변 |
| `refinement_summary` | `string` | yes | - | 셀 근거를 통해 확인/수정된 사항 요약 |
| `direct_cells` | `array<DirectCellDTO>` | no | - | DB 메타데이터에서 직접 인출된 셀 정보 목록 |
| `model` | `string` | yes | - | 답변 개선에 사용된 LLM 모델 ID |
| `api_usage` | `ApiUsageDTO` | yes | - | LLM 토큰 사용량 |
| `latency_seconds` | `number` | yes | - | 모듈 실행 시간(초) |
| `estimated_cost_usd` | `number` | yes | - | 예상 API 비용(USD) |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "answer_json": {
      "replace_with": "AnswerDTO"
    }
  },
  "config": {
    "model": "gpt-5.6-luna",
    "preset": "luna_cell_refiner",
    "system_prompt": "<use system_prompt default from ConfigDTO>",
    "user_prompt_template": "<use user_prompt_template default from ConfigDTO>",
    "cell_extractor_prompt": "<use cell_extractor_prompt default from ConfigDTO>",
    "max_direct_cells": 25
  }
}
```

```bash
python -m backend.tools.run_module answer_refiner --contract
python -m backend.tools.run_module answer_refiner --request request.json
```

HTTP에서는 `POST /api/modules/answer_refiner/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
