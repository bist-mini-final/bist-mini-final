# [BP-004] 프로젝트 마일스톤 타임라인 & 역할 분배(R&R) 명세서
> **Document Code:** `BP-004` | **Domain:** 00. Master Plan & Standards | **Status:** Approved Baseline  
> **Classification:** Project WBS, 3-Phase MVP Milestones & 4-Lead Role Distribution Matrix

---

## 1. 3차 MVP 개발 마일스톤 타임라인 (3-Phase MVP Milestones)

`bist-mini-final` 플랫폼은 체계적인 **3차 MVP(Minimum Viable Product) 단계**를 거쳐 점진적으로 구축 및 고도화되었습니다:

```mermaid
gantt
    title bist-mini-final 3차 MVP 엔지니어링 마일스톤 타임라인
    dateFormat  YYYY-MM-DD
    section 1차 MVP: 기반 데이터 & 코어 RAG
    엑셀 2D 좌표 파서 & VLM 표 기하 감지   :done, mvp1_1, 2026-07-01, 7d
    PostgreSQL Binary COPY 적재 파이프라인 :done, mvp1_2, after mvp1_1, 7d
    FRTR 재무 RAG 프레임워크 조사 & 틀 정립  :done, mvp1_3, 2026-07-01, 10d
    IBM 재무제표 수집 및 1차 평가셋 구축   :done, mvp1_4, after mvp1_3, 7d
    section 2차 MVP: 재무 BI, 쿼리 라우팅 & 오케스트레이션
    2-Tier DAG 오케스트레이션 엔진 & FSM   :done, mvp2_1, after mvp1_2, 10d
    시맨틱/LLM 쿼리 라우터 (데이터 스코프 제한):done, mvp2_2, after mvp2_1, 7d
    40+ 재무비율 엔진 & Financial BI 대시보드 :done, mvp2_3, after mvp1_4, 10d
    가상 기업(비스텔리젼스/콜드플레이) 재무제표 제작:done, mvp2_4, after mvp2_3, 7d
    section 3차 MVP: 챗봇, 기업 비교, BI 고도화 & 전사 거버넌스
    AI 금융 대화형 챗봇 (Fast RAG 연동)    :done, mvp3_1, after mvp2_2, 10d
    기업 비교 인사이트 & 듀퐁 크로스 분석   :done, mvp3_2, after mvp2_4, 10d
    BI 대시보드 인터랙션 고도화 & 감사 모달:done, mvp3_3, after mvp2_3, 10d
    전사 코드 리팩토링, AST 계약검증 & 25개 청사진:done, mvp3_4, after mvp3_1, 7d
```

---

## 2. 4인 전담 엔지니어링 Lead 역할 분배 매트릭스 (R&R Matrix)

| 엔지니어 (Role) | 1차 MVP (기반 데이터 & 코어 RAG) | 2차 MVP (오케스트레이션, 라우팅 & BI) | 3차 MVP (챗봇, 비교 & 인터랙션 고도화/거버넌스) | 연계 청사진 |
| :--- | :--- | :--- | :--- | :---: |
| **김지환**<br>*(Team Lead)* | • OpenPyXL 2D 셀 좌표 파서<br>• Luna VLM 표 바운딩박스 검출<br>• PostgreSQL Native Binary COPY 파이프라인 구축 | • 2-Tier DAG 오케스트레이션 엔진 구축<br>• 런타임 FSM 및 노드 상태 전이기 구현<br>• PR 코드 리뷰, 브랜치 머지 및 충돌 관리 | • 전사 코드베이스 리팩토링 및 클린 계층화<br>• AST 아키텍처 계약 테스트(`test_architecture_contracts.py`)<br>• 8대 도메인 25개 마스터 청사진 거버넌스 확립 | [`BP-101`](file:///c:/Repos/bist-mini-final/docs/01_system_blueprints/BP-101_system_architecture_blueprint.md)<br>[`BP-103`](file:///c:/Repos/bist-mini-final/docs/01_system_blueprints/BP-103_concurrency_and_locking_model.md)<br>[`BP-201`](file:///c:/Repos/bist-mini-final/docs/02_data_engine_blueprints/BP-201_spreadsheet_coordinate_parser.md)<br>[`BP-203`](file:///c:/Repos/bist-mini-final/docs/02_data_engine_blueprints/BP-203_binary_copy_vector_pipeline.md)<br>[`BP-301`](file:///c:/Repos/bist-mini-final/docs/03_pipeline_module_blueprints/BP-301_dag_execution_engine.md)<br>[`BP-401`](file:///c:/Repos/bist-mini-final/docs/04_workspace_blueprints/BP-401_ws_pipeline_playground.md) |
| **전명준**<br>*(Data & Evaluation Lead)* | • IBM 원천 재무제표 엑셀 분석<br>• 1차 Ground-Truth 재무 Q&A 평가 데이터셋 구축<br>• 재무 데이터 무결성 검증 | • 가상 기업(비스텔리젼스, 콜드플레이) 모델링<br>• 다중 시트 합성 재무제표(`.xlsx`) 데이터셋 제작<br>• 다년도 계정과목 매핑 정규화 | • 다중 기업 듀퐁 3단계(순이익률x자산회전율x레버리지) 크로스 비교 엔진 구현<br>• 동종업계 5각 재무 건전성 레이더 차트 및 벤치마크 랭킹 인사이트 뷰 구축<br>• 다중 기업 통화/단위 정규화 모델 | [`BP-001`](file:///c:/Repos/bist-mini-final/docs/00_master_plan_and_standards/BP-001_business_vision_and_executive_summary.md)<br>[`BP-405`](file:///c:/Repos/bist-mini-final/docs/04_workspace_blueprints/BP-405_ws_company_comparison.md)<br>[`BP-701`](file:///c:/Repos/bist-mini-final/docs/07_validation_blueprints/BP-701_contract_testing_and_benchmarks.md) |
| **권혁준**<br>*(RAG Framework & BI Lead)*| • FRTR(Financial RAG/Table Retrieval) 재무 RAG 방법론 프레임워크 조사<br>• Dense+Sparse 기초 검색 방법론 틀 정립 | • 40+ 전사 재무비율 무손실 `Decimal` 계산 엔진(`FinancialCalculatorModule`) 구현<br>• 5개년 건전성 히트맵 및 기본 Financial BI 대시보드 구축 | • **Financial BI 대시보드 고도화 (적응형 음수 마진 Y축 동적 스케일링 엔진 `chartViewModel.ts`)**<br>• **원천 엑셀 셀 감사 추적 `EvidenceDialog` & Web a11y 표준 모달 시스템(`useModalDialog.ts`) 연동**<br>• **BI 스냅샷 렌더링 및 캐시 최적화** | [`BP-002`](file:///c:/Repos/bist-mini-final/docs/00_master_plan_and_standards/BP-002_core_use_cases_and_workflows.md)<br>[`BP-303`](file:///c:/Repos/bist-mini-final/docs/03_pipeline_module_blueprints/BP-303_hybrid_retrieval_and_fusion.md)<br>[`BP-403`](file:///c:/Repos/bist-mini-final/docs/04_workspace_blueprints/BP-403_ws_financial_bi_analytics.md) |
| **김정원**<br>*(Query Optimization & Chatbot Lead)* | • 재무 자연어 질의 분석 및 서브쿼리 분해 방법론 조사<br>• 쿼리 라우팅 기초 구조 탐색 | • `SemanticQueryRouter` & `LlmQueryRouter` 개발을 통한 대상 기업/시트 데이터 스코프(Data Scope) 제한기 구현<br>• 불필요 검색 범위 축소를 통한 토큰/비용 최적화 | • AI 금융 대화형 챗봇(/chatbot) 풀스택 구축<br>• `FastRagPipelineAdapter` 인메모리 연동 (<300ms 초고속 응답)<br>• 대화 세션 컨텍스트 및 마크다운/LaTeX 수식 실시간 SSE 스트리밍 구현 | [`BP-302`](file:///c:/Repos/bist-mini-final/docs/03_pipeline_module_blueprints/BP-302_21_modules_pinout_catalog.md)<br>[`BP-404`](file:///c:/Repos/bist-mini-final/docs/04_workspace_blueprints/BP-404_ws_ai_financial_chatbot.md)<br>[`BP-502`](file:///c:/Repos/bist-mini-final/docs/05_interface_blueprints/BP-502_sse_streaming_protocol.md) |

---

## 3. 3단계 MVP별 상세 WBS 내역

```text
[1차 MVP: 기반 데이터 수집, 파싱 & 코어 RAG 적재]
  ├── WBS 1.1 (김지환): OpenPyXL 병합 해제 및 2D 직교 좌표계 정규화 파서 개발
  ├── WBS 1.2 (김지환): Luna VLM 1-Shot 표 바운딩박스 검출 및 header_with_value 직렬화기 구현
  ├── WBS 1.3 (김지환): PostgreSQL Native Binary COPY 3072d 고속 벌크 주입기 구축
  ├── WBS 1.4 (권혁준): FRTR 재무 RAG 방법론 프레임워크 조사 및 Dense+Sparse 기초 검색 틀 정립
  └── WBS 1.5 (전명준): IBM 원천 재무제표 엑셀 분석 및 1차 Ground-Truth 평가 데이터셋 구축

[2차 MVP: 2-Tier 오케스트레이션, 쿼리 스코프 라우팅 & 재무 BI 대시보드]
  ├── WBS 2.1 (김지환): Kahn 위상정렬 기반 2-Tier DAG 실행기, FSM 런타임 및 PR 머지/품질 관리
  ├── WBS 2.2 (김정원): SemanticQueryRouter & LlmQueryRouter를 통한 대상 기업/시트 데이터 스코프 제한기 개발
  ├── WBS 2.3 (권혁준): 40+ 전사 재무비율 무손실 Decimal 계산 엔진 및 Financial BI 대시보드 차트 구축
  ├── WBS 2.4 (권혁준): 회계기간/통화 프로파일러 연동 및 5개년 건전성 히트맵 뷰모델 구현
  └── WBS 2.5 (전명준): 가상 기업(비스텔리젼스, 콜드플레이) 모델링 및 복합 다중 시트 재무제표(.xlsx) 제작

[3차 MVP: AI 챗봇, 다중 기업 비교, BI 고도화 & 전사 아키텍처 거버넌스]
  ├── WBS 3.1 (김정원): Fast RAG 인메모리 어댑터 연동 및 AI 금융 대화형 챗봇(/chatbot) 풀스택 구축
  ├── WBS 3.2 (김정원): 챗봇 대화 세션 컨텍스트 및 마크다운/LaTeX 수식 실시간 SSE 스트리밍 구현
  ├── WBS 3.3 (전명준): 다중 기업 듀퐁 3단계(순이익률 x 총자산회전율 x 재무레버리지) 크로스 비교 엔진 구현
  ├── WBS 3.4 (전명준): 동종업계 5각 재무 건전성 레이더 차트 및 벤치마크 랭킹 인사이트 뷰 구축
  ├── WBS 3.5 (권혁준): Financial BI 대시보드 인터랙션 고도화 (적응형 음수 마진 Y축 스케일링, 원천 감사 셀 EvidenceDialog 및 a11y 표준 모달 시스템 연동)
  └── WBS 3.6 (김지환): 전사 코드베이스 리팩토링, AST 아키텍처 계약 테스트 체계 및 8대 도메인 25개 청사진 완성
```
