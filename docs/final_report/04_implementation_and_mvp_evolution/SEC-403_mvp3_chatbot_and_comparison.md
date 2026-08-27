# [SEC-403] [3차 MVP] AI 금융 챗봇, 기업 듀퐁 비교 & UI/a11y 고도화
> **Chapter:** 4. 시스템 구현 및 3단계 MVP 진화 과정 | **Section:** 4.3 | **Status:** Approved Baseline  
> **Classification:** MVP 3 Implementation Results: Full-Stack AI Chatbot, DuPont Comparison & a11y UI

---

## 1. 3차 MVP 핵심 과제 및 구현 목표

* **목표**: 실시간 대화형 AI 금융 챗봇 풀스택 구축, 다중 기업 듀퐁 3단계 크로스 비교 인사이트 엔진 개발, 프론트엔드 a11y 표준 모달 및 인터랙션 고도화.
* **주관 엔지니어**: **김정원 (AI Chatbot)**, **전명준 (DuPont Comparison)**, **권혁준 (BI Interaction & a11y)**, **김지환 (Refactoring Governance)**.

---

## 2. 세부 구현 산출물 및 고도화 내역

### 1. AI 금융 대화형 챗봇 ([`backend/features/chatbot/`](file:///c:/Repos/bist-mini-final/backend/features/chatbot/), [`frontend/src/features/chatbot/ChatbotView.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/features/chatbot/ChatbotView.tsx))
* **백엔드 아키텍처**:
  - `ChatSessionRepository`: PostgreSQL 기반 세션/메시지/첨부파일 영구 저장소.
  - `ChatSuggestionService`: DB에 색인된 기업 목록(`bi_companies`)을 기반으로 일별/컨텍스트별 스마트 추천 질문 자동 생성.
  - `compact_evidence` & `save_upload`: 대화 중 사용자가 첨부한 엑셀/CSV 스프레드시트의 텍스트 추출 및 압축 바인딩.
  - `_repair_inline_markdown_tables`: LLM이 한 줄로 출력한 마크다운 GFM 테이블 자동 복원 엔진.
* **프론트엔드 UI/UX (`ChatbotView.tsx`)**:
  - 세션 사이드바(생성/조회/삭제/이름수정) + 실시간 메시지 버블 + 추천 질문 칩(Chips).
  - 마크다운 및 LaTeX 수식 실시간 렌더링, 인라인 차트 시각화(`visualization`), 원천 감사 셀 태그 바인딩.

### 2. 다중 기업 듀퐁 크로스 비교 엔진 ([`BP-405`](file:///c:/Repos/bist-mini-final/docs/blueprints/04_workspace_blueprints/BP-405_ws_company_comparison.md))
* 이종 통화/단위 자동 정규화, $\text{ROE} = \text{PM} \times \text{AT} \times \text{FL}$ 3단계 분해 트리 및 동종업계 5각 건전성 레이더 차트 랭킹 시각화.

### 3. Financial BI 대시보드 인터랙션 고도화 ([`BP-601`](file:///c:/Repos/bist-mini-final/docs/blueprints/06_frontend_blueprints/BP-601_frontend_component_wiring.md))
* 영업적자 음수 마진 적응형 Y축 동적 스케일링 엔진(`getProfitabilityMarginDomain`) 및 `useModalDialog` a11y 표준 모달 시스템 연동.