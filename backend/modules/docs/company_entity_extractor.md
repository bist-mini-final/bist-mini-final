# Company Entity Extractor

> Module type: `company_entity_extractor` · Category: `VLM Vision` · Version: `2`

선택된 Excel 워크북에서 기업명과 티커를 추출합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `input`
- Output ports: `output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | 선택된 processed Excel 파일명 |
| `workbook_hash` | `string` | yes | - | 파일 변경을 식별하는 SHA-256 |
| `sheet_names` | `array<string>` | yes | - | 내부·빈 시트를 제외한 처리 대상 시트명 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `model` | `string` | no | `"gpt-5.6-luna"` | 기업 엔티티 추출에 사용할 LLM 모델 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `company_name` | `string` | no | `""` | 공식 기업명 |
| `ticker` | `string` | no | `""` | 티커 심볼 (없으면 빈 문자열) |
| `display_name` | `string` | no | `""` | '기업명 (TICKER)' 형식 표시명 |
| `confidence` | `string` | no | `"low"` | 추출 신뢰도 (high/medium/low) |
| `source` | `string` | no | `"heuristic"` | 추출 방법 (llm / heuristic) |

## Referenced DTOs

참조 DTO가 없습니다.

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "file_name": "example.xlsx",
    "workbook_hash": "<workbook_hash>",
    "sheet_names": []
  },
  "config": {
    "model": "gpt-5.6-luna"
  }
}
```

```bash
python -m backend.tools.run_module company_entity_extractor --contract
python -m backend.tools.run_module company_entity_extractor --request request.json
```

HTTP에서는 `POST /api/modules/company_entity_extractor/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
