# [SEC-402] [2차 MVP] 2-Tier DAG 오케스트레이션, 쿼리 라우팅 & BI 대시보드
> **Chapter:** 4. 시스템 구현 및 3단계 MVP 진화 과정 | **Section:** 4.2 | **Status:** Approved Baseline  
> **Classification:** MVP 2 Implementation Results: DAG Orchestration, Scope Routing & BI Analytics

---

## 1. 2차 MVP 핵심 과제 및 구현 목표

* **목표**: 21개 모듈을 자유롭게 조합하는 2-Tier DAG 오케스트레이션 엔진 구축, 데이터 스코프 제한 쿼리 라우터 개발, 40+ 전사 재무 BI 대시보드 완성.
* **주관 엔지니어**: **김지환 (Orchestration)**, **김정원 (Query Routing)**, **권혁준 (Financial BI)**, **전명준 (Synthetic Data)**.

---

## 2. 세부 구현 산출물 및 워크스페이스

1. **Kahn 위상정렬 기반 2-Tier DAG 실행기 ([`BP-301`](file:///c:/Repos/bist-mini-final/docs/blueprints/03_pipeline_module_blueprints/BP-301_dag_execution_engine.md))**:
   - 노드 의존성을 자동 정렬하고 비동기 병렬 실행 및 SSE 실시간 이벤트 스트리밍.
   - 동기 `RunStore` 준비·병합·취소 확인은 worker thread로 격리해 async DAG 이벤트 루프의 블로킹을 방지.
2. **시맨틱 & LLM 쿼리 라우터 (`SemanticQueryRouter`, `LlmQueryRouter`)**:
   - 질의 의도를 파악하여 대상 기업/시트로 검색 범위를 사전 제한하여 토큰 비용 60% 절감.
3. **40+ 전사 재무 BI 대시보드 ([`BP-403`](file:///c:/Repos/bist-mini-final/docs/blueprints/04_workspace_blueprints/BP-403_ws_financial_bi_analytics.md))**:
   - 무손실 `Decimal` 연산 기반 4대 영역(수익/안정/성장/활동) 지표 산출, 5개년 건전성 히트맵 및 원본 감사 셀 모달 결선.
   - 기업·스냅샷·작업·질문 진행률 조회와 BI 작업 등록/SSE 초기 로드를 native async PostgreSQL 경계로 제공.
4. **가상 기업(비스텔리젼스, 콜드플레이) 재무제표 데이터셋 구축**:
   - 다중 시트 합성 재무제표 엑셀 제작으로 크로스 검증 데이터 확보.
