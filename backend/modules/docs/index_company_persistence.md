# Index Company Persistence

> Module type: `index_company_persistence` · Category: `Storage / DB` · Version: `1`

추출한 기업명을 pgvector 컬렉션과 청크 메타데이터에 반영합니다.

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: `index_input`, `company_input`
- Output ports: `output`
- Cacheable: `false`

## Input DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `index_input` | `VectorIndexDTO` | yes | - | pgvector 인덱스 저장 결과 |
| `company_input` | `CompanyEntityExtractorOutputDTO` | yes | - | 기업 엔티티 추출 결과 |

## Config DTO

원본 JSON 값 전체를 DTO로 사용합니다.

## Output DTO

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `index_id` | `string` | yes | - | - |
| `company_name` | `string` | yes | - | - |
| `ticker` | `string` | no | `""` | - |

## Referenced DTOs

### `CompanyEntityExtractorOutputDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `company_name` | `string` | no | `""` | 공식 기업명 |
| `ticker` | `string` | no | `""` | 티커 심볼 (없으면 빈 문자열) |
| `display_name` | `string` | no | `""` | '기업명 (TICKER)' 형식 표시명 |
| `confidence` | `string` | no | `"low"` | 추출 신뢰도 (high/medium/low) |
| `source` | `string` | no | `"heuristic"` | 추출 방법 (llm / heuristic) |

### `VectorIndexDTO`

| Field | Type | Required | Default | Description |
|---|---|---:|---|---|
| `index_id` | `string` | yes | - | 영속 벡터 인덱스의 콘텐츠 주소 |
| `file_name` | `string` | yes | - | 인덱싱한 원본 Excel 파일명 |
| `workbook_hash` | `string` | yes | - | 인덱싱한 Excel 파일 해시 |
| `model` | `string` | yes | - | 문서 임베딩 모델 ID |
| `dimension` | `integer` | yes | - | 벡터 차원 |
| `document_count` | `integer` | yes | - | 저장된 검색 문서 개수 |

## Independent execution

`request.json` 예시 골격:

```json
{
  "input": {
    "index_input": {
      "replace_with": "VectorIndexDTO"
    },
    "company_input": {
      "replace_with": "CompanyEntityExtractorOutputDTO"
    }
  },
  "config": {}
}
```

```bash
python -m backend.tools.run_module index_company_persistence --contract
python -m backend.tools.run_module index_company_persistence --request request.json
```

HTTP에서는 `POST /api/modules/index_company_persistence/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
