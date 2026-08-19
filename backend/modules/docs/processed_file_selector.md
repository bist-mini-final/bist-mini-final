# Processed Excel File Selector

> Module type: `processed_file_selector` · Category: `Source` · Version: `2`

data/processed의 Excel 파일 하나를 안전하게 선택합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: 없음(Source)
- Output ports: `output`
- Cacheable: `false`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | data/processed에서 선택할 Excel 파일명 |
| `sheet_names` | `array<string> \| null` | no | `null` | 처리할 표시 시트 목록. 생략하면 모든 표시 시트를 선택합니다. |

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | 선택된 processed Excel 파일명 |
| `workbook_hash` | `string` | yes | - | 파일 변경을 식별하는 SHA-256 |
| `sheet_names` | `array<string>` | yes | - | 내부·빈 시트를 제외한 처리 대상 시트명 |

## Referenced DTOs

참조 DTO가 없습니다.

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "file_name": "example.xlsx"
  },
  "config": {}
}
```

```bash
python -m backend.tools.run_module processed_file_selector --contract
python -m backend.tools.run_module processed_file_selector --request request.json
```

HTTP에서는 `POST /api/modules/processed_file_selector/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
