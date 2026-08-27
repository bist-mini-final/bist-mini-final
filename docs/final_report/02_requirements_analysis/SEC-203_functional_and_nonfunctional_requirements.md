# [SEC-203] 기능적(FR) 및 비기능적(NFR) 요구사항 명세서
> **Chapter:** 2. 프로젝트 요구 분석 | **Section:** 2.3 | **Status:** Approved Baseline  
> **Classification:** Functional & Non-Functional Requirements Specification (IEEE 830 Standard)

---

## 1. 기능적 요구사항 명세 (Functional Requirements, FR)

| 요구사항 ID | 요구사항 명칭 | 세부 기능 명세 및 입출력 기준 | 연계 컴포넌트 |
| :--- | :--- | :--- | :--- |
| **FR-1** | **재무 엑셀 시트 2D 파싱 및 VLM 구조화** | • OpenPyXL을 통한 병합 셀 값 전파 및 2D 직교 좌표계 정규화.<br>• GPT-5.6 Luna VLM을 통해 표 경계 및 헤더 계층 바운딩박스 자동 감지.<br>• `header_with_value` 단일 정규 포맷 직렬화. | `structure.cell_text_serializer`<br>`structure.luna_vlm_structure_detector` |
| **FR-2** | **PostgreSQL pgvector 초고속 벌크 색인** | • `text-embedding-3-large` 3072d Dense 임베딩 생성.<br>• PostgreSQL Native `Binary COPY` 스트리밍 파이프라인으로 초당 대량 벡터 주입.<br>• HNSW 코사인 인덱스 및 Full-Text TSVector 인덱스 자동 갱신. | `backend/storage/pgvector_binary_copy.py`<br>`retrieval.text_embedder` |
| **FR-3** | **2-Tier DAG 실행 및 시각적 샌드박스** | • Kahn 위상 정렬 기반의 2-Tier DAG 실행 엔진 및 FSM 상태 전이.<br>• React Flow 2D 캔버스 기반 노드 결선 및 Config 튜닝.<br>• Server-Sent Events(SSE) 기반 실시간 상태/지연/비용 스트리밍. | `backend/engine/workflows/`<br>`frontend/src/features/playground/` |
| **FR-4** | **40+ 전사 재무 BI 분석 및 감사 추적** | • 회계기간(FY/LTM), 통화, 배율 단위 1-Shot 자동 프로파일링.<br>• 40개 이상 핵심 재무 비율(수익/안정/성장/활동) 무손실 고정소수점 산출.<br>• 5개년 건전성 히트맵 및 원본 엑셀 셀 좌표 1:1 바인딩 감사 모달. | `backend/features/bi/`<br>`modules/reader/financial_calculator.py` |
| **FR-5** | **Fast RAG 대화형 챗봇 & 기업 듀퐁 비교** | • <300ms 초고속 인메모리 Fast RAG 어댑터 및 마크다운/LaTeX 수식 답변 스트리밍.<br>• 2개 이상 복수 기업 통화/단위 정규화 및 듀퐁 3단계 분해 트리 크로스 비교. | `backend/features/bi/fast_rag_adapter.py`<br>`frontend/src/pages/CompanyComparisonPage.tsx` |

---

## 2. 비기능적 요구사항 명세 (Non-Functional Requirements, NFR)

| 요구사항 ID | 품질 속성 (Quality Attribute) | 비기능적 제약 및 아키텍처 보장 기준 (Guarantee) | 검증 메커니즘 |
| :--- | :--- | :--- | :--- |
| **NFR-1** | **성능 및 지연시간 (Latency)** | • Fast RAG 단일 질의응답 P95 처리시간 $< 500\text{ms}$ 보장.<br>• 2-Tier 분리를 통해 대규모 배치 적재 중에도 챗봇 응답 지연율 0%. | 벤치마크 하네스 ([`SEC-501`](file:///c:/Repos/bist-mini-final/docs/final_report/05_validation_and_conclusion/SEC-501_benchmark_evaluation_plan.md)) |
| **NFR-2** | **수치 무결성 (Integrity)** | • 모든 재무 비율 계산 시 `decimal.Decimal` 고정소수점 연산 강제.<br>• 듀퐁 3단계 항등식($\text{ROE} = \text{PM} \times \text{AT} \times \text{FL}$) 산술 오차 0.000% 보장. | 단위 테스트 (`tests/features/bi/`) |
| **NFR-3** | **동시성 및 가용성 (Concurrency)** | • Kubernetes 환경에서 3-Level 분산 락 (`SKIP LOCKED` + `pg_advisory_lock` + 5초 하트비트 Lease) 적용.<br>• 워커 OOM 크래시 시 30초 내 고아 작업 자동 회수(`STALLED` ➡️ `queued`). | 분산 락 런북 ([`SEC-303`](file:///c:/Repos/bist-mini-final/docs/final_report/03_system_architecture_and_design/SEC-303_sequence_diagrams.md)) |
| **NFR-4** | **소프트웨어 헌법 (Governance)** | • Pydantic v2 DTO 100% 엄격 타입화.<br>• AST 정적 계약 검사를 통해 Layer Inversion 및 레이어 침범 0건 영구 보장. | AST 계약 테스트 ([`SEC-502`](file:///c:/Repos/bist-mini-final/docs/final_report/05_validation_and_conclusion/SEC-502_contract_testing_results.md)) |
| **NFR-5** | **UI 접근성 및 톤앤매너 (a11y & Design)** | • 무이모티콘 & `lucide-react` SVG 벡터 아이콘 표준화.<br>• Web a11y 표준 준수 포커스 트랩 및 ESC 닫기 모달 훅(`useModalDialog.ts`) 적용. | 프론트엔드 표준 ([`SEC-307`](file:///c:/Repos/bist-mini-final/docs/final_report/03_system_architecture_and_design/SEC-307_engineering_standards_and_tokens.md)) |
