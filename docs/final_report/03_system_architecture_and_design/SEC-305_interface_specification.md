# [SEC-305] 인터페이스 설계 (REST API & SSE 스트리밍 규격)
> **Chapter:** 3. 시스템 아키텍처 및 상세 설계 | **Section:** 3.5 | **Status:** Approved Baseline  
> **Classification:** Interface Control Document (ICD), FastAPI REST API & Chatbot/Workflow Protocols

---

## 1. REST API 핵심 엔드포인트 규격 (REST API Matrix)

| 도메인 | 메서드 & URL Path | 요청 DTO / 파라미터 | 응답 DTO 및 반환 데이터 | 핵심 비즈니스 로직 |
| :--- | :--- | :--- | :--- | :--- |
| **AI Chatbot** | `GET /api/chatbot/sessions` | `client_id: str` (Query) | `List[ChatSessionDTO]` | 클라이언트별 세션 목록 인출 (`updated_at DESC`) |
| | `POST /api/chatbot/sessions` | `CreateSessionRequest(client_id)` | `ChatSessionDTO(session_id, title)` | 신규 대화 세션 컨텍스트 생성 |
| | `GET /api/chatbot/sessions/{id}` | `session_id: str, client_id: str` | `ChatSessionDetailDTO(messages, attachments)` | 세션 상세 내역 및 메시지 히스토리 조회 |
| | `PATCH /api/chatbot/sessions/{id}` | `RenameSessionRequest(title)` | `ChatSessionDTO(session_id, title)` | 대화 세션 제목 수정 |
| | `DELETE /api/chatbot/sessions/{id}` | `session_id, client_id` | `{"deleted": true}` | 대화 세션 및 연계 메시지/첨부파일 완전 삭제 |
| | `POST /api/chatbot/sessions/{id}/messages` | `CreateMessageRequest(content, attachment_id)` | `MessageResponseDTO(content, visualization, status)` | RAG 파이프라인 연동 실시간 답변 및 차트 생성 |
| | `POST /api/chatbot/sessions/{id}/attachments` | `file: UploadFile, client_id: str` | `AttachmentDTO(attachment_id, file_name, preview)` | 대화 컨텍스트용 엑셀/CSV 첨부파일 업로드 |
| | `GET /api/chatbot/suggestions` | `client_id: str` (Query) | `List[str]` | 현재 등록된 기업/지표 기반 스마트 추천 질문 |
| **Data Sources** | `POST /api/data-sources/upload` | `file: UploadFile` | `UploadResponseDTO(file_id, total_sheets)` | 엑셀 파싱 및 워크북 해시(`SHA-256`) 생성 |
| | `POST /api/data-sources/index` | `IndexRequestDTO(file_id)` | `IndexResultDTO(indexed_vectors, status)` | VLM 표 검출 및 Binary COPY 벌크 주입 |
| **Workflows** | `POST /api/workflows/run` | `RunWorkflowRequest(dag_topology)` | `WorkflowRunLease(run_id, token, status)` | 2-Tier DAG 실행 대기열 등록 |
| | `GET /api/workflows/{id}/stream` | `run_id: str` (Path) | `text/event-stream` (SSE Event Frames) | 노드 상태 전이 및 청크 실시간 스트리밍 |
| **Financial BI** | `GET /api/bi/companies` | `limit: int = 50` | `List[CompanyProfileDTO]` | 등록 기업 목록 및 메타데이터 인출 |
| | `GET /api/bi/companies/{id}/dashboard`| `company_id: str` (Path) | `BiDashboardSnapshotDTO(40+ ratios)` | 40+ 지표 무손실 연산 스냅샷 조회 |
| | `POST /api/bi/companies/{id}/refresh` | `company_id: str` (Path) | `BiRefreshResponseDTO(job_id)` | 최신 엑셀 기준 지표 재연산 트리거 |
| **Comparison** | `POST /api/bi/comparison/matrix` | `ComparisonRequestDTO(comp_ids)` | `CompanyComparisonMatrixDTO(radar, dupont)`| 다중 기업 통화/단위 정규화 & 듀퐁 3단계 분해 |