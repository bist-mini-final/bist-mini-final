# [SEC-402] [2차 MVP 및 현재화] Durable DAG와 Financial BI
> **Chapter:** 4. 시스템 구현 및 MVP 진화 | **Section:** 4.2 | **Status:** Current Historical Record

---

## 1. 초기 목표와 현재 결과

2차 MVP는 조합 가능한 DAG, 질의 scope routing, 재무 BI 화면을 결합했습니다. 이후 실제 코드 기준으로 다음과 같이 현재화했습니다.

| 초기 표현 | 현재 운영 계약 |
| :--- | :--- |
| 21개 pipeline module | `ModuleRegistry`에 등록된 19개 module type |
| 2-Tier/in-memory 실행 선택 | PostgreSQL durable queue + KEDA one-shot worker |
| 40개 이상 BI ratio | 명시적으로 지원하는 21개 BI metric |
| synthetic company 중심 데모 | 업로드 workbook에서 발행된 실제 BI snapshot |
| 일반 BI 안의 기업 비교 | 별도 Company Comparison API와 snapshot 도메인 |

---

## 2. 구현 산출물

1. Kahn 위상 정렬과 cycle validation을 수행하는 DAG executor.
2. 동일 위상 노드를 `TaskGroup`으로 병렬 실행하고 노드별 상태를 안전하게 병합하는 async 실행 경로.
3. query decomposition, scope routing, Dense/keyword retrieval, RRF, 2D context expansion, reader를 조합하는 19개 module catalog.
4. PostgreSQL에 run/node 상태, lease, heartbeat를 저장하고 Redis 신호로 SSE 재조회 지연을 줄이는 durable control plane.
5. 기업·문서 profile·materialization job·question/answer·dashboard snapshot을 분리한 BI 도메인.
6. `Decimal` 기반 파생식과 21개 metric, 원본 셀 evidence를 표시하는 Financial BI UI.
7. 준비된 대시보드 기업 목록과 스냅샷 생성 후보를 분리하고, 사용자가 선택한 기업만 KEDA materialization queue에 등록하는 스냅샷 관리 UI.

---

## 3. 범위 결정

- Cross-Encoder reranker는 추가하지 않습니다.
- 검색 기준선은 Dense + PostgreSQL keyword + RRF입니다.
- BI metric ID가 없거나 evidence가 불완전한 값은 화면 편의를 위해 합성하지 않습니다.
- Company Comparison은 BI의 검증 snapshot을 읽지만 자체 API와 버전형 결과를 소유합니다.
