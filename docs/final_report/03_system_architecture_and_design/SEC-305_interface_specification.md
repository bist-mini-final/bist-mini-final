# [SEC-305] 인터페이스 설계 (REST API & SSE 스트리밍 규격)
> **Chapter:** 3. 시스템 아키텍처 및 상세 설계 | **Section:** 3.5 | **Status:** Approved Baseline  
> **Classification:** Interface Control Document (ICD), FastAPI REST API & Chatbot/Workflow Protocols

---

## 1. REST API 핵심 엔드포인트 규격 (REST API Matrix)

| 도메인 | 메서드 & URL Path | 요청 DTO / 파라미터 | 응답 DTO 및 반환 데이터 | 핵심 비즈니스 로직 |
| :--- | :--- | :--- | :--- | :--- |
| **AI Chatbot** | `GET/POST /api/v1/chat/sessions` | `client_id` / `CreateSessionRequest` | 세션 목록 또는 세션 DTO | 세션 조회·생성 |
| | `GET/PATCH/DELETE /api/v1/chat/sessions/{id}` | 세션 ID와 client ID | 세션 상세·수정·삭제 응답 | 대화 히스토리 관리 |
| | `POST /api/v1/chat/sessions/{id}/messages` | `CreateMessageRequest` | 메시지·run DTO (202) | RAG 실행 등록 또는 직접 답변 |
| | `GET /api/v1/chat/runs/{run_id}` | `client_id` | run·동기화된 메시지 DTO | durable RAG 결과 동기화 |
| | `POST /api/v1/chat/sessions/{id}/attachments` | `UploadFile` | 첨부 DTO | 대화 컨텍스트 파일 저장 |
| **Data Sources** | `POST /api/v1/data-sources/files/upload` | `UploadFile`, `auto_ingest` | 파일·ingestion job 응답 | 업로드 및 선택적 큐 등록 |
| | `POST/GET /api/v1/data-sources/ingestion-jobs` | ingestion request | durable run DTO | 인덱싱 작업 등록·조회 |
| **Workflows** | `POST /api/v1/workflows/{id}/runs` | `WorkflowExecutionRequest` | `WorkflowRun` (202) | durable DAG 실행 등록 |
| | `GET /api/v1/runs/{id}/stream` | `run_id` | `text/event-stream` | 저장된 실행 상태의 SSE 전송 |
| **Financial BI** | `GET /api/v1/bi/companies` | - | 기업 목록 DTO | 등록 기업 목록 조회 |
| | `GET /api/v1/bi/companies/{id}/dashboard`| `company_id` | `BiDashboardSnapshot` | 근거 기반 스냅샷 조회 |
| | `POST /api/v1/bi/companies/{id}/refresh` | `company_id` | `BiDashboardSnapshot` | 파생 지표 재계산 |
| **Comparison** | `GET /api/v1/company-comparisons/league` | None | `FinancialLeagueResponse(standings, rankings)` | BI 대시보드와 분리된 기업 비교 리그 테이블 랭킹 인출 |
| | `POST /api/v1/company-comparisons/analyze` | `CompanyComparisonRequest(base, target)` | `CompanyComparisonResponse(dupont, radar, delta)` | 다중 기업 듀퐁 3단계 분해 및 크로스 비교 분석 |
