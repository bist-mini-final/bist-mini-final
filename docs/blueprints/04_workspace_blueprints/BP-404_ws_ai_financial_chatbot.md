# [BP-404] AI Financial Chatbot 워크스페이스 명세서
> **Document Code:** `BP-404` | **Category:** Workspace Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`frontend/src/features/chatbot/ChatbotView.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/features/chatbot/ChatbotView.tsx), [`backend/features/chatbot/api_routes.py`](file:///c:/Repos/bist-mini-final/backend/features/chatbot/api_routes.py), [`backend/features/chatbot/repository.py`](file:///c:/Repos/bist-mini-final/backend/features/chatbot/repository.py)

---

## 1. AI 금융 대화형 챗봇 아키텍처 개요

AI 금융 챗봇은 자연어 재무 질의에 대해 **PostgreSQL 기반 대화 세션 컨텍스트**, **스마트 추천 질문**, **엑셀/CSV 첨부파일 컨텍스트 바인딩**, **Fast RAG 하이브리드 검색** 및 **마크다운/LaTeX/인라인 차트 시각화**를 제공합니다:

```mermaid
flowchart TD
    UI["ChatbotView (React 18 SPA)"] <-->|REST API| ROUTER["FastAPI Chatbot Router (/api/v1/chat)"]
    
    subgraph ChatServices ["Chatbot Core Services"]
        REPO["ChatSessionRepository (chat_sessions, chat_messages)"]
        SUGG["ChatSuggestionService (Dynamic Financial Prompts)"]
        ATTACH["Attachment Processor (compact_evidence / save_upload)"]
        TABLE_REP["Inline Markdown Table Repair Engine"]
    end

    ROUTER <--> REPO
    ROUTER <--> SUGG
    ROUTER <--> ATTACH
    ROUTER --> TABLE_REP
    ROUTER <-->|RAG Execution| PIPELINE["RAG Pipeline Job / FastRagAdapter"]
    PIPELINE <--> PG[("PostgreSQL 16 (pgvector + FTS)")]
```

---

## 2. 핵심 엔드포인트 명세

정식 경로는 `/api/v1/chat`입니다. 문서가 과거에 사용한 `/api/chatbot` 및 버전 경로 `/api/v1/chatbot`은 호환 별칭으로 유지합니다.

* `GET /api/v1/chat/sessions`: 세션 목록 조회
* `POST /api/v1/chat/sessions`: 세션 생성
* `GET /api/v1/chat/sessions/{session_id}`: 세션 상세 및 메시지 히스토리 조회
* `PATCH /api/v1/chat/sessions/{session_id}`: 세션 제목 수정
* `DELETE /api/v1/chat/sessions/{session_id}`: 세션 삭제
* `POST /api/v1/chat/sessions/{session_id}/messages`: 메시지 전송 및 답변/시각화 생성
* `POST /api/v1/chat/sessions/{session_id}/attachments`: 엑셀/CSV 첨부파일 업로드
* `GET /api/v1/chat/suggestions`: 동적 스마트 질문 추천
