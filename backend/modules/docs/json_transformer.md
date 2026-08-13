# JSON Format Mapper

> Module type: `json_transformer` · Category: `Transform` · Version: `1`

입력 JSON의 필드명을 매핑 규칙에 따라 변환합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `any_json`
- Output ports: `transformed_json`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `any_json` | `object` | yes | - | 변환할 임의 JSON 객체; 최상위 키만 이름 변경 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `mappings` | `object<string, string>` | no | - | source_field: target_field 형식의 필드명 매핑 규칙 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `transformed_json` | `object` | yes | - | 매핑 규칙이 적용된 JSON 객체 출력 포트 |

## Referenced DTOs

참조 DTO가 없습니다.

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "any_json": {}
  },
  "config": {
    "mappings": {}
  }
}
```

```bash
python -m backend.tools.run_module json_transformer --contract
python -m backend.tools.run_module json_transformer --request request.json
```

HTTP에서는 `POST /api/modules/json_transformer/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
