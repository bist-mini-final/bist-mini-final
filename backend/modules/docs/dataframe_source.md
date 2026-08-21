# DataFrame Source (Code RAG)

> Module type: `dataframe_source` · Category: `Source` · Version: `1`

Excel 파일을 pandas DataFrame으로 읽어 시트별 스키마와 샘플을 출력합니다. LLM Code Agent가 pandas 코드를 작성할 때 참조할 DataFrame 컨텍스트를 제공합니다. (Code Execution RAG 시연용)

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: 없음(Source)
- Output ports: `output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | data/processed에서 선택할 Excel 파일명 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `sample_rows` | `integer` | no | `3` | 각 시트에서 추출할 샘플 행 수 (0이면 스키마만) |
| `max_sheets` | `integer` | no | `5` | 출력에 포함할 최대 시트 수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `total_sheets` | `integer` | yes | - | - |
| `sheets` | `array<SheetSchemaDTO>` | yes | - | - |
| `variable_hint` | `string` | yes | - | LLM 코드 에이전트에 전달할 DataFrame 변수명 힌트 |

## Referenced DTOs

### `SheetSchemaDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `sheet_name` | `string` | yes | - | - |
| `row_count` | `integer` | yes | - | - |
| `column_count` | `integer` | yes | - | - |
| `columns` | `array<string>` | yes | - | - |
| `dtypes` | `object<string, string>` | yes | - | - |
| `sample` | `array<object>` | yes | - | - |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "file_name": "example.xlsx"
  },
  "config": {
    "sample_rows": 3,
    "max_sheets": 5
  }
}
```

```bash
python -m backend.tools.run_module dataframe_source --contract
python -m backend.tools.run_module dataframe_source --request request.json
```

HTTP에서는 `POST /api/modules/dataframe_source/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
