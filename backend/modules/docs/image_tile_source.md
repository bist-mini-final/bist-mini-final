# Image Tile Source (PixelRAG)

> Module type: `image_tile_source` · Category: `Source` · Version: `1`

Excel 시트를 행 단위로 타일링한 이미지 목록을 출력합니다. PixelRAG 파이프라인에서 Qwen3-VL 비전 임베딩의 입력으로 사용됩니다. 타일은 data/artifacts/spreadsheets/ 경로에 사전 렌더링되어야 합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: 없음(Source)
- Output ports: `output`
- Cacheable: `true`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | data/source_files에서 선택할 Excel 파일명 (이미지 타일 소스로 사용) |
| `sheet_name` | `string \| null` | no | `null` | 특정 시트만 선택. 비워두면 모든 시트 포함 |

## Config DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `tile_height_px` | `integer` | no | `64` | 행 단위 타일 높이 (픽셀). PixelRAG 타일링 단위와 일치해야 합니다 |
| `max_tiles` | `integer` | no | `500` | 출력할 최대 타일 수 |

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `file_name` | `string` | yes | - | - |
| `workbook_hash` | `string` | yes | - | - |
| `total_tiles` | `integer` | yes | - | - |
| `tile_height_px` | `integer` | yes | - | - |
| `tiles` | `array<ImageTileDTO>` | yes | - | - |
| `artifact_dir` | `string` | yes | - | 이미지 타일 저장 기준 디렉터리 |
| `pipeline_note` | `string` | no | `"PixelRAG: 각 타일을 Qwen3-VL-Embedding-2B로 벡터화하여 FAISS 인덱스에 저장한 뒤 VLM(GPT-5.6 Luna)으로 답변을 생성합니다."` | - |

## Referenced DTOs

### `ImageTileDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `tile_id` | `string` | yes | - | 타일 고유 ID (sheet_row 형식) |
| `sheet_name` | `string` | yes | - | - |
| `row_range` | `array<integer>` | yes | - | [row_start, row_end] 픽셀 범위 |
| `relative_path` | `string` | yes | - | data/artifacts/spreadsheets/ 기준 상대 경로 |
| `exists` | `boolean` | yes | - | 실제 파일 존재 여부 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "file_name": "example.xlsx"
  },
  "config": {
    "tile_height_px": 64,
    "max_tiles": 500
  }
}
```

```bash
python -m backend.tools.run_module image_tile_source --contract
python -m backend.tools.run_module image_tile_source --request request.json
```

HTTP에서는 `POST /api/modules/image_tile_source/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
