# [BP-501] REST API와 DTO 규격
> **Document Code:** `BP-501` | **Contract State:** Target Architecture | **Capability State:** Operational | **Structure State:** Complete
> **Target Ownership:** `backend/domains/*/presentation`, `backend/api/router.py`, `backend/api/middleware.py`, `backend/api/exception_handlers.py`, `backend/api/versioning.py`
> **Current References:** [`backend/api/router.py`](../../../backend/api/router.py), [`backend/api/openapi.py`](../../../backend/api/openapi.py), [`backend/api/exception_handlers.py`](../../../backend/api/exception_handlers.py), [`backend/domains/workflow/presentation/`](../../../backend/domains/workflow/presentation), [`backend/domains/data_sources/presentation/`](../../../backend/domains/data_sources/presentation)

---

## 1. Namespace와 호환 정책

- 정식 제품 namespace는 `/api/v1`입니다.
- `/api`는 `Deprecation`과 replacement `Link` header를 제공하는 OpenAPI 비노출 호환 alias입니다.
- chatbot 정식 경로는 `/api/v1/chat`; `/api/v1/chatbot`은 문서 호환 alias입니다.
- OpenAPI, frontend client, 새 문서는 정식 경로만 사용합니다.
- health probe `/healthz`, `/livez`, `/readyz`는 version namespace 밖에 있습니다.

---

## 2. 공개 endpoint 계약

### BI와 Company Comparison

| Method | Path | 역할 |
| :--- | :--- | :--- |
| GET | `/api/v1/bi/companies` | active BI 기업 목록 |
| GET | `/api/v1/bi/materialization-candidates` | 스냅샷 생성 가능 기업과 `not_created\|source_changed\|failed` 사유 |
| GET | `/api/v1/bi/companies/{company_id}/dashboard` | current BI dashboard snapshot |
| DELETE | `/api/v1/bi/companies/{company_id}/dashboard` | 기업 BI snapshot 삭제 |
| POST | `/api/v1/bi/materializations` | BI materialization job 등록 |
| GET | `/api/v1/bi/materializations/{job_id}` | 작업 상태 |
| GET | `/api/v1/bi/materializations/{job_id}/stream` | 작업 SSE |
| POST | `/api/v1/bi/companies/{company_id}/refresh` | dashboard 재계산 |
| POST | `/api/v1/bi/companies/{company_id}/reset` | question batch 재등록 |
| GET | `/api/v1/bi/question-jobs/{job_id}` | question batch 진행률 |
| GET | `/api/v1/bi/question-jobs/{job_id}/stream` | question batch SSE |
| GET | `/api/v1/company-comparisons/snapshot` | current comparison snapshot |
| POST | `/api/v1/company-comparisons/snapshot/refresh` | BI source 검증·비교 snapshot 발행 |

과거 `/bi/comparisons`, `/company-comparisons/league`, `/company-comparisons/analyze`는 제거됐습니다.

### Chat

| Method | Path | 역할 |
| :--- | :--- | :--- |
| GET/POST | `/api/v1/chat/sessions` | 세션 목록/생성 |
| GET/PATCH/DELETE | `/api/v1/chat/sessions/{session_id}` | 세션 상세/이름 변경/삭제 |
| POST | `/api/v1/chat/sessions/{session_id}/messages` | 메시지와 durable RAG run 등록 |
| POST | `/api/v1/chat/sessions/{session_id}/attachments` | 첨부 저장·추출 |
| GET | `/api/v1/chat/runs/{run_id}` | RAG run과 메시지 동기화 |
| GET | `/api/v1/chat/suggestions` | 추천 질문 |
| POST | `/api/v1/chat/suggestions/refresh` | 추천 질문 갱신 |

### Workflow와 module

| Method | Path | 역할 |
| :--- | :--- | :--- |
| GET | `/api/v1/workflows` | workflow 목록 |
| GET/PUT/DELETE | `/api/v1/workflows/{workflow_id}` | 정의 조회/저장/삭제 |
| POST | `/api/v1/workflows/{workflow_id}/runs` | durable run 등록 |
| GET | `/api/v1/runs` | run 목록 |
| GET | `/api/v1/runs/{run_id}` | run 상태 |
| GET | `/api/v1/runs/{run_id}/nodes/{node_id}` | 단일 node 실행 상태·입력·출력 |
| POST | `/api/v1/runs/{run_id}/resume` | 재개/재등록 |
| POST | `/api/v1/runs/{run_id}/cancel` | 취소 요청 |
| GET | `/api/v1/runs/{run_id}/stream` | run SSE |
| GET | `/api/v1/modules` | 19개 등록 module 목록 |
| GET | `/api/v1/modules/categories` | category별 catalog |
| GET | `/api/v1/modules/schemas` | input/config/output JSON schema |
| GET | `/api/v1/modules/{module_type}` | 단일 module 계약 |
| GET | `/api/v1/modules/{module_type}/docs` | 단일 module Markdown |

### Data Sources와 artifact

| Method | Path | 역할 |
| :--- | :--- | :--- |
| GET/POST | `/api/v1/data-sources/ingestion-jobs` | ingestion 목록/등록 |
| GET/DELETE | `/api/v1/data-sources/ingestion-jobs/{run_id}` | 상태/삭제 |
| GET | `/api/v1/data-sources/ingestion-jobs/by-index/{index_id}` | index별 최신 작업 |
| POST | `/api/v1/data-sources/ingestion-jobs/{run_id}/resume` | 재개 |
| POST | `/api/v1/data-sources/ingestion-jobs/{run_id}/cancel` | 취소 |
| GET | `/api/v1/data-sources/files` | 파일 목록 |
| POST | `/api/v1/data-sources/files/upload` | 파일 업로드 |
| GET | `/api/v1/data-sources/files/{filename}/preview` | workbook preview |
| GET | `/api/v1/data-sources/files/{filename}/download` | 원본 다운로드 |
| DELETE | `/api/v1/data-sources/files/{filename}` | 파일 삭제 |
| GET | `/api/v1/data-sources/indexes` | index 목록 |
| GET/DELETE | `/api/v1/data-sources/indexes/{index_id}` | index 조회/삭제 |
| PUT | `/api/v1/data-sources/indexes/{index_id}/company` | index-company 연결 |
| POST | `/api/v1/data-sources/indexes/{index_id}/search` | scoped vector/keyword 검색 |
| GET | `/api/v1/data-sources/db-status` | 현재 DB probe |
| POST | `/api/v1/data-sources/db-connect` | 지정 DB 연결 검사 |
| GET | `/api/v1/spreadsheet-artifacts/{workbook_hash}/sheets/{sheet_name}` | render artifact |
| GET | `/api/v1/evidence/cells/resolve` | 셀 인용 query를 workbook·sheet image·bbox 근거로 해석 |

### Benchmark, jobs, maintenance

| Method | Path | 역할 |
| :--- | :--- | :--- |
| GET | `/api/v1/benchmark-sets` | benchmark set 목록 |
| POST | `/api/v1/benchmarks/jobs` | benchmark job 등록 |
| GET/DELETE | `/api/v1/benchmarks/jobs/{job_id}` | 상태/삭제 |
| POST | `/api/v1/benchmarks/jobs/{job_id}/pause` | pause 요청 |
| POST | `/api/v1/benchmarks/jobs/{job_id}/resume` | resume |
| GET | `/api/v1/benchmarks` | 완료 평가 목록 |
| GET | `/api/v1/benchmarks/{benchmark_id}` | 평가 상세 |
| GET | `/api/v1/jobs` | KEDA/Job/Pod와 queue/lease 읽기 전용 snapshot |
| DELETE | `/api/v1/cache` | pipeline cache 정리 |

---

## 3. 오류 계약

모든 framework/domain 오류는 다음 공통 envelope로 정규화합니다.

```json
{
  "detail": {
    "code": "COMPANY_COMPARISON_SNAPSHOT_NOT_FOUND",
    "message": "발행된 기업 비교 스냅샷이 없습니다.",
    "retryable": true,
    "context": {}
  }
}
```

- Pydantic/domain validation: 422
- 존재하지 않는 resource/current snapshot: 404
- source data가 publish 조건을 충족하지 못함: 409
- provider 또는 일시적 인프라 장애: 5xx와 `retryable=true`
- 예상하지 못한 내부 예외: 민감한 stack/detail을 숨긴 `INTERNAL_SERVER_ERROR`

Router는 `HTTPException`에 `code`, `message`, `retryable`, 선택적 `context`를 전달하고 전역 handler가 envelope를 만듭니다. Pydantic validation, `PipelineBaseError`, 일반 예외도 동일한 모양으로 변환됩니다.

---

## 4. DTO와 OpenAPI 규칙

- request/response는 Pydantic model로 선언합니다.
- module catalog의 input/config/output schema도 OpenAPI components에 주입합니다.
- 새 정식 route는 `/api/v1` OpenAPI에 나타나야 하고 compatibility route는 `include_in_schema=False`여야 합니다.
- frontend는 TypeScript type만 신뢰하지 않고 외부 JSON을 Zod로 runtime 검증합니다.
- comparison snapshot은 source/evidence/assumption/rank link를 model validator로 검증합니다.
- route 변경은 [`tests/modules/test_openapi_and_module_routes.py`](../../../tests/modules/test_openapi_and_module_routes.py)와 frontend client tests를 함께 갱신합니다.
- route 함수는 request binding, application command/query 호출과 HTTP response projection만 담당하고 저장소·도메인 단계를 직접 조율하지 않습니다. 별도 HTTP controller가 필요하더라도 해당 domain presentation 내부에 두며 `backend/api`로 올리지 않습니다.
- 현재 OpenAPI는 63개 정식 path와 73개 HTTP operation을 노출합니다. compatibility alias는 이 수와 schema에서 제외합니다.

---

## 5. 소유권과 구조 완료 조건

- 각 domain presentation은 자신의 router, Pydantic schema, HTTP error mapping과 OpenAPI tag를 소유합니다.
- `backend/api/router.py`는 domain router를 결합하고 middleware, exception handler와 versioning만 적용합니다.
- application DTO와 HTTP DTO를 동일 객체로 강제하지 않으며 presentation mapping을 명시적으로 둡니다.
- `backend/api`에는 router composition, middleware, exception/error mapping, versioning, OpenAPI, SPA와 system probe만 남아 있고 도메인 route/controller/schema는 각 presentation에 있습니다.
- API package allowlist와 OpenAPI contract test가 이 경계를 hard gate로 검증합니다.
- method/path/status/error envelope를 바꾸면 해당 domain BP, frontend client/runtime schema, OpenAPI test와 이 문서를 같은 변경에서 갱신합니다.
