# QA Example Bank Loader

> Module type: `qa_example_loader` · Category: `Source` · Version: `1`

시맨틱 쿼리 매칭 라우팅에 사용할 QA 예시 뱅크를 로드합니다. 질문 임베딩 유사도 검색으로 '어떤 파일/시트를 참조해야 하는가'를 결정하는 데 사용됩니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: 없음(Source)
- Output ports: `output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string \| null` | no | `null` | data/qa_examples/ 아래의 JSON 파일명. 비워두면 내장 예시 세트를 사용합니다. |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `include_builtin` | `boolean` | no | `true` | 내장 예시 세트를 함께 포함할지 여부 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `examples` | `array<QaExampleItem>` | yes | - | - |
| `total_count` | `integer` | yes | - | 로드된 예시 총 개수 |
| `source` | `string` | yes | - | 로드 소스 ('builtin' / 파일명) |

## Referenced DTOs

### `QaExampleItem`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `question` | `string` | yes | - | 예시 질문 텍스트 |
| `route` | `string` | yes | - | 라우팅 대상 (파일/시트/파이프라인) |
| `sheet` | `string` | yes | - | 참조할 시트명 |
| `description` | `string` | no | `""` | 질문 유형 설명 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {},
  "config": {
    "include_builtin": true
  }
}
```

```bash
python -m backend.tools.run_module qa_example_loader --contract
python -m backend.tools.run_module qa_example_loader --request request.json
```

HTTP에서는 `POST /api/modules/qa_example_loader/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
