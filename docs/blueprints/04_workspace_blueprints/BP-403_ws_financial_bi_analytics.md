# [BP-403] Financial BI Analytics 워크스페이스

> **Document Code:** `BP-403` | **Category:** Workspace & Financial Analytics | **Status:** Implemented & Operational
> **Canonical Source:** [`backend/domains/bi/application/`](file:///c:/Repos/bist-mini-final/backend/domains/bi/application/), [`backend/features/bi/`](file:///c:/Repos/bist-mini-final/backend/features/bi/), [`frontend/src/features/bi/`](file:///c:/Repos/bist-mini-final/frontend/src/features/bi/)

---

## 1. 제품 경계와 데이터 흐름

Financial BI는 한 기업의 검증된 재무 관측값·파생값·원본 셀 근거를 `BiDashboardSnapshot`으로 발행하는 도메인입니다. Company Comparison은 이 current snapshot들을 읽지만 BI API·DTO·저장 수명주기를 대체하지 않습니다.

```mermaid
flowchart LR
    INDEX[Indexed workbook] --> PROFILE[DocumentProfiler]
    PROFILE --> PLAN[Metric question plan]
    PLAN --> QUEUE[BI question durable queue]
    QUEUE --> RAG[Hybrid retrieval and metric reader]
    RAG --> ANSWERS[(bi_questions and bi_answers)]
    ANSWERS --> BUILD[BiQuestionSnapshotMaterializer and calculator]
    BUILD --> SNAP[(bi_dashboard_snapshots)]
    SNAP --> API[GET /api/v1/bi/companies/{id}/dashboard]
    API --> UI[/dashboard]
    SNAP -. read-only source .-> COMP[Company Comparison]
```

- materialization과 metric question은 PostgreSQL queue와 KEDA one-shot worker에서 처리합니다.
- 기업·스냅샷·작업 조회와 SSE 초기 로드는 async PostgreSQL pool을 사용합니다.
- Redis는 materialization/question SSE의 변경 신호이며 PostgreSQL 상태가 source of truth입니다.

## 2. 21개 지표 계약

현재 목록은 `backend/domains/bi/domain/models.py::MetricId`와 `backend/domains/bi/domain/catalog.py::METRIC_CATALOG`가 결정합니다.

| 종류 | 지표 |
| :--- | :--- |
| 원천 amount | `revenue`, `operating_income`, `net_income`, `operating_cash_flow`, `capital_expenditure`, `cash_and_short_term_investments`, `short_term_debt`, `current_portion_of_long_term_debt`, `long_term_debt`, `total_assets`, `total_liabilities`, `total_equity` |
| 원천 우선 + 구성요소 fallback | `total_debt` |
| 파생 amount | `free_cash_flow`, `net_debt` |
| 파생 percent | `revenue_yoy_growth`, `operating_margin`, `net_margin`, `free_cash_flow_margin`, `debt_ratio`, `net_debt_ratio` |

ROE, ROA, 유동비율, 당좌비율과 총자산회전율은 현재 `MetricId`에 없으므로 API 제공 지표로 문서화하지 않습니다.

## 3. 계산·근거 무결성

- amount 지표는 ISO 4217 통화와 `ones|thousands|millions|billions` 배율을 명시합니다.
- 원천 수치가 없거나 모호하면 `missing|ambiguous|invalid|not_meaningful` 상태를 사용하며 임의 값을 만들지 않습니다.
- `calculator.py`는 `Decimal`을 사용하고 `formulas.json`·`formula_dsl.py`의 허용된 산술식만 평가합니다.
- 파생값은 입력 관측값의 `BiEvidence`를 합쳐 시트명·셀 좌표·원문을 보존합니다.
- FY와 LTM은 `BiPeriod.kind`로 구분합니다. `calendar_periods.py`는 회계연도 종료일을 비교 가능한 달력 축으로 표현하지만 연간 값을 분기 실적으로 환산하지 않습니다.

## 4. API와 사용자 제어

| 메서드 | 경로 | 역할 |
| :--- | :--- | :--- |
| `GET` | `/api/v1/bi/companies` | current snapshot을 가진 기업 목록 |
| `GET` | `/api/v1/bi/materialization-candidates` | 인덱싱 완료 후 스냅샷 미생성·원본 변경·생성 실패 기업 목록 |
| `GET` | `/api/v1/bi/companies/{company_id}/dashboard` | 현재 `BiDashboardSnapshot` 조회 |
| `POST` | `/api/v1/bi/materializations` | 신규 BI materialization 등록 |
| `GET` | `/api/v1/bi/materializations/{job_id}` | 작업 상태 조회 |
| `GET` | `/api/v1/bi/materializations/{job_id}/stream` | materialization SSE |
| `POST` | `/api/v1/bi/companies/{company_id}/refresh` | 기존 관측값으로 파생값 재계산 |
| `POST` | `/api/v1/bi/companies/{company_id}/reset` | 질문·답변 교체 작업 등록 |
| `GET` | `/api/v1/bi/question-jobs/{job_id}` | 질문 배치 진행률 |
| `GET` | `/api/v1/bi/question-jobs/{job_id}/stream` | 질문 배치 SSE |

프런트는 `CompanySelector`, `SnapshotManager`, `useSelectedBiCompany`, `BiDashboardGrid`, 지표별 차트, `EvidenceDialog`, reset/layout dialog를 조합합니다. 대시보드 기업 목록 필터는 유지하며, 사용자는 `기업 스냅샷 추가`에서 후보를 명시적으로 선택해야 유료 materialization 작업을 시작합니다. 작업 완료 후 기업 목록을 다시 조회해 새 스냅샷을 자동 선택합니다. `/bi`는 `/dashboard`의 호환 alias입니다.

## 5. Company Comparison 연계 규칙

1. 기업 비교는 `PostgresBiStore.list_companies_async()`와 `get_current_many_async()`로 BI current head만 읽습니다.
2. BI 스냅샷을 수정하지 않으며 결과를 `CompanyComparisonSnapshot`으로 별도 발행합니다.
3. 비교 최신 FY의 매출·영업이익·총부채·총자산·순부채와 근거가 모두 있어야 점수 계산에 포함됩니다.
4. BI의 21개 지표 계약 변경 시 Company Comparison source fingerprint와 정책 버전을 함께 검토합니다.

세부 비교 계약은 [`BP-405`](file:///c:/Repos/bist-mini-final/docs/blueprints/04_workspace_blueprints/BP-405_ws_company_comparison.md)를 따릅니다.
