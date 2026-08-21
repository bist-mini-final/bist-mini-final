# Financial Formula Calculator

> Module type: `financial_formula_calculator` · Category: `Logic` · Version: `1`

컨텍스트에서 재무 수치를 추출하고 Python 엔진으로 오차 없는 결정론적 연산(비율, 증감률 등)을 수행합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `context_json`
- Output ports: `formula_result`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `context_json` | `ContextDTO` | yes | - | Context Expander로부터 전달된 시계열 및 셀 컨텍스트 블록 DTO |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"gpt-5.6-luna"` | 수식 파싱 및 변수 추출에 사용할 LLM ID |
| `enabled` | `boolean` | no | `true` | 계산 모듈 활성화 여부 |
| `calc_keywords` | `array<string>` | no | - | 계산 실행 트리거 키워드 목록 |
| `max_context_blocks` | `integer` | no | `50` | 수식 계산기에 전달할 최대 컨텍스트 블록 수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `is_calculation_required` | `boolean` | yes | - | - |
| `calculated_metrics` | `array<CalculatedMetricDTO>` | no | - | - |
| `summary_text` | `string` | no | `""` | - |
| `formula_result` | `object \| null` | no | `null` | - |

## Referenced DTOs

### `CalculatedMetricDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `metric_name` | `string` | yes | - | - |
| `formula` | `string` | yes | - | - |
| `variables` | `object` | yes | - | - |
| `computed_value` | `number \| null` | no | `null` | - |
| `formatted_result` | `string` | yes | - | - |
| `unit` | `string` | yes | - | - |

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
    "enabled": true,
    "calc_keywords": [],
    "max_context_blocks": 50
  }
}
```

```bash
python -m backend.tools.run_module financial_formula_calculator --contract
python -m backend.tools.run_module financial_formula_calculator --request request.json
```

HTTP에서는 `POST /api/modules/financial_formula_calculator/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
