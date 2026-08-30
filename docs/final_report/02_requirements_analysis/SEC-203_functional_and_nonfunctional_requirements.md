# [SEC-203] 기능적·비기능적 요구사항 명세

> **Chapter:** 2. 프로젝트 요구 분석 | **Section:** 2.3 | **Status:** Implementation-aligned

---

## 1. 기능적 요구사항

| ID | 요구사항 | 현재 수용 기준 |
| :--- | :--- | :--- |
| FR-1 | 데이터 소스 관리 | Excel 업로드·목록·미리보기·다운로드·soft delete, index 검색·기업 연결, ingestion job 등록·조회·취소·재개 제공 |
| FR-2 | 파이프라인 설계·실행 | 19개 등록 모듈 contract 조회, workflow CRUD, run 등록·조회·취소·재개와 SSE 제공 |
| FR-3 | Financial BI | 기업 목록, 21개 지표 `BiDashboardSnapshot`, materialization/question job과 SSE, refresh/reset 제공 |
| FR-4 | AI Financial Chat | 세션 CRUD, 메시지·첨부, durable RAG run 조회, 추천 질문 조회·갱신 제공 |
| FR-5 | Company Comparison | `/company-comparison` 단일 UI, current/refresh snapshot API, 최소 2개 기업 검증, 근거·제외·가정·정책 버전 제공 |
| FR-6 | 운영·배포 | health/live/ready probe, `/jobs` 읽기 전용 관제, Docker/Helm/KEDA와 Alembic migration 제공 |

## 2. 비기능적 요구사항

| ID | 품질 속성 | 보장 기준 | 검증 |
| :--- | :--- | :--- | :--- |
| NFR-1 | 무결성 | BI 파생식은 `Decimal`; 비교는 동일 FY·통화·배율과 근거를 요구하고 synthetic fallback 금지 | BI·comparison 단위 테스트 |
| NFR-2 | 영속성 | 실행 상태·BI·chat·comparison head는 PostgreSQL이 source of truth | migration·repository·API 테스트 |
| NFR-3 | 동시성 | queue claim, advisory lock, lease token·heartbeat로 중복 완료와 stale worker 덮어쓰기 방지 | workflow/K8s 계약 테스트 |
| NFR-4 | 비차단 API | async DB/provider를 우선하고 동기 I/O는 thread 또는 one-shot worker에 격리 | async boundary 계약 테스트 |
| NFR-5 | 계약 안정성 | Pydantic DTO, Zod 응답 검증, `/api/v1` canonical prefix, 표준 에러 envelope | OpenAPI·frontend schema 테스트 |
| NFR-6 | 감사 가능성 | soft delete, append-only audit log, 원본 셀 evidence와 불변 snapshot history | Alembic·DB contract 테스트 |
| NFR-7 | 접근성 | route registry 일원화, Lucide 아이콘, 키보드·focus·dialog 계약 | frontend component tests |

성능·정확도 KPI는 [`SEC-501`](file:///c:/Repos/bist-mini-final/docs/final_report/05_validation_and_conclusion/SEC-501_benchmark_evaluation_plan.md)의 측정 목표이며, 운영 측정 없이 달성값으로 간주하지 않습니다.
