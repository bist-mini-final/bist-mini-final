# [SEC-305] REST API와 SSE 인터페이스

> **Chapter:** 3. 시스템 아키텍처 및 상세 설계 | **Section:** 3.5 | **Status:** Implementation-aligned

---

## 1. API 원칙

- canonical prefix는 `/api/v1`입니다. `/api`는 OpenAPI에 노출하지 않는 호환 prefix입니다.
- request/response는 Pydantic DTO, 프런트 응답은 Zod schema로 검증합니다.
- 에러는 공통 envelope로 변환하며 도메인 오류와 내부 오류를 구분합니다.
- OpenAPI `/openapi.json`이 세부 DTO와 메서드의 실행 기준입니다.

## 2. 도메인 namespace

| namespace | 책임 |
| :--- | :--- |
| `/api/v1/modules`, `/workflows`, `/runs` | module introspection과 durable DAG |
| `/api/v1/data-sources` | 파일·index·ingestion |
| `/api/v1/bi` | 기업별 BI snapshot·materialization·question jobs |
| `/api/v1/chat` | 세션·메시지·첨부·RAG run·suggestions |
| `/api/v1/company-comparisons` | 별도 기업 비교 current/refresh snapshot |
| `/api/v1/benchmarks` | 평가 job·result |
| `/api/v1/jobs` | Kubernetes read-only 관제 |

BI의 `/companies`는 준비됐거나 생성 중인 대시보드 기업만 반환합니다. 인덱싱됐지만 아직 대시보드에 노출되지 않는 기업은 `/bi/materialization-candidates`에서 별도로 조회하며, 사용자의 명시적 생성 요청 후 current snapshot이 발행되면 기존 기업 목록 필터를 통과합니다.

## 3. Company Comparison 계약

| 메서드 | 경로 | 정상 응답 | 주요 오류 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/company-comparisons/snapshot` | current `CompanyComparisonSnapshot` | 발행본 없음 `404` |
| `POST` | `/api/v1/company-comparisons/snapshot/refresh` | 기존 또는 신규 `CompanyComparisonSnapshot` | 완전 기업 2개 미만 `409` |

과거 `/bi/comparisons`, `/company-comparisons/league`, `/company-comparisons/analyze`는 제거했습니다. BI와 Company Comparison의 프런트 탭·API·DTO를 합치지 않습니다.

전체 endpoint matrix와 에러 형식은 [`BP-501`](file:///c:/Repos/bist-mini-final/docs/blueprints/05_interface_blueprints/BP-501_rest_api_specification.md), SSE reconnect·heartbeat는 [`BP-502`](file:///c:/Repos/bist-mini-final/docs/blueprints/05_interface_blueprints/BP-502_sse_streaming_protocol.md)를 따릅니다.
