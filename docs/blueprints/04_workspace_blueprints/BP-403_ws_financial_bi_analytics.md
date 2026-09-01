# [BP-403] Financial BI Analytics 워크스페이스

> **Document Code:** `BP-403` | **Contract State:** Target Architecture | **Capability State:** Operational | **Structure State:** Complete
> **Target Ownership:** `backend/domains/bi`, `backend/platform/postgres`, `frontend/src/features/bi`, `frontend/src/pages`
> **Current References:** [`backend/domains/bi/`](../../../backend/domains/bi), [`backend/bootstrap/bi.py`](../../../backend/bootstrap/bi.py), [`frontend/src/features/bi/`](../../../frontend/src/features/bi)

---

## 1. 제품 경계와 데이터 흐름

Financial BI는 한 기업의 검증된 재무 관측값·파생값·원본 셀 근거를 `BiDashboardSnapshot`으로 발행하는 도메인입니다. Company Comparison은 이 current snapshot들을 읽지만 BI API·DTO·저장 수명주기를 대체하지 않습니다.

```mermaid
flowchart LR
    SOURCE[Original workbook] -->|force rebuild for new snapshot| PROFILE[(data sources WorkbookProfile)]
    INDEX[Indexed workbook] --> SOURCE
    PROFILE --> ADAPTER[BI profile adapter]
    ADAPTER --> PLAN[Metric question plan]
    INDEX -. freshly rebuilt profile incomplete only .-> FALLBACK[Retrieval and LLM profiler]
    FALLBACK --> ADAPTER
    PLAN --> QUEUE[BI question durable queue]
    QUEUE --> EXACT{Catalog exact evidence}
    EXACT -->|match| READER[Structured metric reader]
    EXACT -->|no match| RAG[Hybrid retrieval and context expansion]
    RAG --> READER
    READER --> ANSWERS[(bi_questions and bi_answers)]
    ANSWERS --> BUILD[BiQuestionSnapshotMaterializer and calculator]
    BUILD --> SNAP[(bi_dashboard_snapshots)]
    SNAP --> API[GET /api/v1/bi/companies/{id}/dashboard]
    API --> UI[/dashboard]
    SNAP -. read-only source .-> COMP[Company Comparison]
```

- materialization과 metric question은 PostgreSQL queue와 KEDA one-shot worker에서 처리합니다.
- 기업·스냅샷·작업 조회와 SSE 초기 로드는 async PostgreSQL pool을 사용합니다.
- Redis는 materialization/question SSE의 변경 신호이며 PostgreSQL 상태가 source of truth입니다.
- BI는 `workbook_profiles`를 직접 소유하지 않습니다. data sources 계약의 기간·통화·배율·시트 역할을 BI `BiDocumentProfile`로 변환합니다.
- **신규 BI materialization은 저장된 `workbook_profiles`를 입력 캐시로 사용하지 않습니다.** 원본 hash를 검증한 뒤 resolver를 `force=True`로 실행해 원본 workbook에서 프로필을 다시 계산하고 같은 lineage의 프로필 레코드를 교체합니다. 일반 조회·Reader 단위 보완은 저장된 최신 프로필을 읽을 수 있습니다.
- 새 결정론 프로필에 기간은 있으나 통화·배율이 불완전할 때만 검색/LLM profiler가 누락 필드를 보완합니다. 이때 기간 집합은 방금 원본에서 계산한 값이 우선하며, 과거 저장 프로필과 병합하지 않습니다. 원본 resolver 자체가 실패한 경우에도 검색/LLM 결과를 새 프로필로 교체하고 과거 값은 되살리지 않습니다.

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
- profile의 통화·배율은 Reader가 명시 단위를 반환하지 못한 amount 관측값의 공통 계약으로 사용합니다. 원본에도 명시 근거가 없으면 null을 추정하지 않고 기존 `ambiguous` 규칙을 유지합니다.

### 3.1 원천 지표 검색 순서

1. `PostgresBiMetricEvidenceRetriever`는 현재 질문의 collection·workbook hash·file name lineage 안에서만 조회합니다.
2. `METRIC_CATALOG`의 영문·한글 별칭, row header hint와 excluded alias를 정규화해 동일 지표 행을 찾습니다. `statement_hints`는 우선순위에만 사용하고 특정 sheet 이름을 필수 조건으로 고정하지 않습니다.
3. 같은 좌표의 `header_only`와 `header_with_value` 중 실제 값 문서를 선택하며 `?`, `NA`, `N/A`, `NM`, `#PEND`, `NULL`은 Reader 근거에서 제외합니다.
4. 명시적 LTM header가 있으면 `BiPeriod.kind`와 일치하는 좌표만 선택합니다. 일부 sheet에서 마지막 두 열이 동일 종료일이고 상위 LTM header가 유실된 경우, 같은 지표 행의 중복 종료일 중 왼쪽을 FY·오른쪽을 LTM으로 해석합니다. 열 문자나 특정 vendor sheet 이름은 사용하지 않습니다.
5. 정확 후보가 있으면 scope-aware Decomposer·embedding·Dense/Sparse 검색을 생략하고 구조화 Metric Reader로 전달합니다. 정확 후보가 없을 때만 BP-303 하이브리드 RAG를 실행합니다.
6. 정확 조회와 RAG 모두 값을 찾지 못하면 보조 지표를 다른 의미의 행으로 대체하지 않고 기존 missing/fallback 계산 정책을 따릅니다.

## 4. API와 사용자 제어

| 메서드 | 경로 | 역할 |
| :--- | :--- | :--- |
| `GET` | `/api/v1/bi/companies` | current snapshot을 가진 기업 목록 |
| `GET` | `/api/v1/bi/materialization-candidates` | 인덱싱 완료 후 스냅샷 미생성·원본 변경·생성 실패 기업 목록 |
| `GET` | `/api/v1/bi/companies/{company_id}/dashboard` | 현재 `BiDashboardSnapshot` 조회 |
| `DELETE` | `/api/v1/bi/companies/{company_id}/dashboard` | 해당 기업 current BI snapshot과 대시보드 노출 제거 |
| `POST` | `/api/v1/bi/materializations` | 신규 BI materialization 등록 |
| `GET` | `/api/v1/bi/materializations/{job_id}` | 작업 상태 조회 |
| `GET` | `/api/v1/bi/materializations/{job_id}/stream` | materialization SSE |
| `POST` | `/api/v1/bi/companies/{company_id}/refresh` | 기존 관측값으로 파생값 재계산 |
| `POST` | `/api/v1/bi/companies/{company_id}/reset` | 질문·답변 교체 작업 등록 |
| `GET` | `/api/v1/bi/question-jobs/{job_id}` | 질문 배치 진행률 |
| `GET` | `/api/v1/bi/question-jobs/{job_id}/stream` | 질문 배치 SSE |

프런트는 `CompanySelector`, `SnapshotManager`, `useSelectedBiCompany`, `BiDashboardGrid`, 지표별 차트, `EvidenceDialog`, reset/layout dialog를 조합합니다. 대시보드 기업 목록 필터는 유지하며, 사용자는 `기업 스냅샷 추가`에서 후보를 명시적으로 선택해야 유료 materialization 작업을 시작합니다. 작업 완료 후 기업 목록을 다시 조회해 새 스냅샷을 자동 선택합니다. `/bi`는 `/dashboard`의 호환 alias입니다.

`materializations`는 원본 workbook 프로필부터 새로 만드는 생성 경계입니다. 반면 `refresh`는 현재 snapshot의 검증 관측값으로 파생값만 재계산하고, `reset`은 현재 snapshot 기간에 대한 지표 질문을 다시 실행합니다. 저장 프로필을 무시한 완전 재생성이 필요하면 기존 snapshot을 삭제한 뒤 materialization을 새로 등록합니다.

## 5. Company Comparison 연계 규칙

1. 기업 비교는 `PostgresBiStore.list_companies_async()`와 `get_current_many_async()`로 BI current head만 읽습니다.
2. BI 스냅샷을 수정하지 않으며 결과를 `CompanyComparisonSnapshot`으로 별도 발행합니다.
3. 비교 최신 FY의 매출·영업이익·총부채·총자산·순부채와 근거가 모두 있어야 점수 계산에 포함됩니다.
4. BI의 21개 지표 계약 변경 시 Company Comparison source fingerprint와 정책 버전을 함께 검토합니다.

세부 비교 계약은 [`BP-405`](BP-405_ws_company_comparison.md)를 따릅니다.

---

## 6. 책임 분리와 구조 완료 조건

- metric definition, evidence requirement와 snapshot publication policy는 BI domain/application이 소유합니다.
- source lookup·snapshot repository·materialization adapter는 BI infrastructure, API/SSE DTO는 BI presentation, durable process는 BI workers에 둡니다.
- metric exact-evidence 조회 port는 BI application이 정의하고 PostgreSQL 구현은 BI infrastructure가 소유합니다. 범용 RAG module이나 data sources 저장 계약에 BI metric 의미를 역류시키지 않습니다.
- Company Comparison은 BI infrastructure를 import하지 않고 BI application의 snapshot reader port만 사용합니다.
- Company Comparison은 공통 workbook profile을 직접 조회하지 않고, 해당 계약이 반영된 current BI snapshot만 소비합니다. 따라서 BI snapshot 생성만으로 비교 head를 자동 발행하지 않는 기존 갱신 경계는 유지됩니다.
- 계산·application port·PostgreSQL/integration adapter·API/SSE·worker가 BI vertical slice로 이동했으며 이전 feature/API 호환 경로는 제거됐습니다.
- 구조 계약 테스트는 BI domain/application/presentation/worker가 feature·storage·platform concrete 구현을 역참조하지 못하게 하며 21개 metric 및 snapshot 회귀 계약을 함께 검증합니다.
- BI 스냅샷 추가/삭제/refresh/reset은 각각 별도 mutation이며 UI는 진행 상태와 실패를 이전 정상 snapshot과 구분합니다.
- BI snapshot 생성만으로 comparison head를 암묵적으로 다시 발행하지 않습니다. 비교 데이터 갱신은 BP-405의 명시적 refresh 계약을 따릅니다.
- metric catalog, 계산식, period/evidence 상태 또는 snapshot schema를 바꾸면 policy/version, comparison source fingerprint와 API/frontend schema를 같은 변경에서 갱신합니다.
