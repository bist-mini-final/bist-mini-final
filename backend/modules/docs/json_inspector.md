# JSON Data Inspector

> Module type: `json_inspector` · Category: `Output` · Version: `2`

원본 JSON을 그대로 전달하고 캔버스에서는 상류 모듈에 맞는 테이블 또는 Markdown 뷰로 미리 봅니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `input`
- Output ports: `output`
- Cacheable: `false`

## Input DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Referenced DTOs

참조 DTO가 없습니다.

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "replace_with": "raw JSON"
  },
  "config": {}
}
```

```bash
python -m backend.tools.run_module json_inspector --contract
python -m backend.tools.run_module json_inspector --request request.json
```

HTTP에서는 `POST /api/modules/json_inspector/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
