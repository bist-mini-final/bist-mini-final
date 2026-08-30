# [SEC-103] 팀 구성 및 역할 분담

> **Chapter:** 1. 프로젝트 개요 | **Section:** 1.3 | **Status:** Historical ownership with current mappings

---

## 1. 프로젝트 역할

| 담당 | 프로젝트 기여 영역 | 현재 코드·문서 연결 |
| :--- | :--- | :--- |
| 김지환 | 시스템 총괄, DAG 실행·배포·리팩토링·품질 거버넌스 | `backend/engine/`, `backend/bootstrap/`, `deploy/`, `tests/modules/` |
| 전명준 | 평가 데이터, 초기 기업 비교 UX·분석 정책 | `backend/features/benchmark/`, `backend/features/company_comparison/`, `frontend/src/features/company-comparison/` |
| 권혁준 | Financial BI와 재무 지표·시각화 | `backend/features/bi/`, `frontend/src/features/bi/` |
| 김정원 | 질의 라우팅과 AI 금융 챗봇 | `modules/query/`, `backend/features/chatbot/`, `frontend/src/features/chatbot/` |

이 표는 팀의 기능 소유 이력을 설명합니다. 현재 코드는 공통 composition root와 계약 테스트를 통해 담당자와 무관하게 동일한 아키텍처 규칙을 따릅니다.

## 2. 현재화 과정에서의 공동 결정

- 과거 21개 모듈 기획은 `ModuleRegistry`에 실제 등록된 19개 모듈 계약으로 정리했습니다.
- BI의 21개 지표와 Company Comparison 점수 정책을 서로 다른 도메인으로 분리했습니다.
- 기존 Company Comparison과 V2의 이중 화면을 `/company-comparison` 하나로 통합했습니다.
- 가상 기업과 임의 보간은 운영 비교 경로에서 제거했습니다.
- 로컬 VLM과 Cross-Encoder reranker는 구현 범위에서 제외했습니다.
- 배포는 PostgreSQL durable queue, Redis 변경 신호, KEDA worker, Helm과 Alembic을 기준으로 통일했습니다.

세부 책임보다 현재 실행 계약이 우선하며, 최신 기준은 [`CURRENT_IMPLEMENTATION_BASELINE.md`](file:///c:/Repos/bist-mini-final/docs/CURRENT_IMPLEMENTATION_BASELINE.md)를 따릅니다.
