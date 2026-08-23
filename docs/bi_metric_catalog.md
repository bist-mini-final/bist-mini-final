# BI 대시보드 메트릭 카탈로그

> **Source**: [`backend/features/bi/catalog.py`](../backend/features/bi/catalog.py)
> **Catalog Version**: `1` | **Formula Version**: `1`

메트릭은 두 종류로 구분됩니다:
- **Source** — LLM이 재무 문서에서 직접 읽어오는 원천 값 (기간×메트릭 조합마다 질문 생성)
- **Derived** — Source 메트릭 값들을 수식으로 계산하는 파생 값 (질문 없음)
- **Fallback** — Source 우선 탐색 후 없으면 구성 메트릭 합산으로 대체

---

## Source 메트릭 (LLM 질문 생성 대상)

질문 템플릿:
```
"이 문서에서 {period_label}의 {metric_label} 값을 찾아라.
 계산하지 말고 원문 값, 통화, 배율, 근거 cell_id를 구조화해 반환하라."
```

| # | Metric ID | 한글 명칭 | 설명 | 역할 | 재무제표 힌트 | 한글 별칭 | 영문 별칭 | 부호 정책 |
|---|-----------|----------|------|------|-------------|---------|---------|---------|
| 1 | `revenue` | 매출 | 기업이 상품과 서비스 판매로 얻은 수익 | PRIMARY | Income Statement, Key Statistics | 매출, 매출액, 영업수익 | Revenue, Total Revenue, Sales | AS_REPORTED |
| 2 | `operating_income` | 영업이익 | 본업에서 발생한 이익 | PRIMARY | Income Statement | 영업이익 | Operating Income, Operating Profit, EBIT | AS_REPORTED |
| 3 | `net_income` | 순이익 | 모든 비용과 세금을 반영한 이익 | PRIMARY | Income Statement | 순이익, 당기순이익 | Net Income, Net Earnings | AS_REPORTED |
| 4 | `operating_cash_flow` | 영업현금흐름 | 영업활동에서 창출된 현금 | PRIMARY | Cash Flow Statement | 영업현금흐름, 영업활동현금흐름 | Operating Cash Flow, Cash from Operations, CFO | AS_REPORTED |
| 5 | `capital_expenditure` | CapEx | 유형 및 무형자산 취득을 위한 지출 | PRIMARY | Cash Flow Statement, Key Statistics | 자본적지출, 설비투자 | Capital Expenditure, CapEx | OUTFLOW_NEGATIVE |
| 6 | `cash_and_short_term_investments` | 현금 및 단기투자자산 | 즉시 활용 가능한 현금성 자산 | PRIMARY | Balance Sheet | 현금 및 단기투자자산, 현금성자산 | Cash and Short-Term Investments, Cash Equivalents | AS_REPORTED |
| 7 | `total_debt` | 총차입금 | 이자 비용이 발생하는 전체 차입금 (Fallback) | PRIMARY | Balance Sheet, Key Statistics | 총차입금, 총부채성차입금 | Total Debt, Gross Debt | AS_REPORTED |
| 8 | `total_assets` | 총자산 | 기업이 보유한 전체 자산 | PRIMARY | Balance Sheet | 총자산 | Total Assets | AS_REPORTED |
| 9 | `total_liabilities` | 총부채 | 기업이 부담하는 전체 부채 | PRIMARY | Balance Sheet | 총부채 | Total Liabilities | AS_REPORTED |
| 10 | `total_equity` | 총자본 | 자산에서 부채를 제외한 주주 지분 | PRIMARY | Balance Sheet | 총자본, 자본총계 | Total Equity, Shareholders' Equity | AS_REPORTED |
| 11 | `short_term_debt` | 단기차입금 | 1년 이내 상환할 차입금 | AUXILIARY | Balance Sheet | 단기차입금 | Short-Term Debt, Short-Term Borrowings | AS_REPORTED |
| 12 | `current_portion_of_long_term_debt` | 유동성 장기부채 | 1년 이내 만기가 도래하는 장기차입금 | AUXILIARY | Balance Sheet | 유동성 장기부채 | Current Portion of Long-Term Debt | AS_REPORTED |
| 13 | `long_term_debt` | 장기차입금 | 1년 이후 상환할 차입금 | AUXILIARY | Balance Sheet | 장기차입금 | Long-Term Debt, Long-Term Borrowings | AS_REPORTED |

> **AUXILIARY** 메트릭 (#11~#13)은 `total_debt` Fallback 계산의 구성 요소로만 사용됩니다.

---

## Fallback 메트릭

Source 탐색 실패 시 구성 메트릭 합산으로 대체합니다.

| Metric ID | 한글 명칭 | Fallback 수식 ID | 구성 메트릭 |
|-----------|----------|----------------|-----------|
| `total_debt` | 총차입금 | `total_debt_components` | `short_term_debt` + `current_portion_of_long_term_debt` + `long_term_debt` |

---

## Derived 메트릭 (수식 계산, 질문 없음)

| # | Metric ID | 한글 명칭 | 설명 | 역할 | 수식 ID | 의존 메트릭 |
|---|-----------|----------|------|------|--------|-----------|
| 1 | `revenue_yoy_growth` | 매출 성장률 | 직전 FY 대비 매출 증감률 | PRIMARY | `revenue_yoy_growth` | `revenue` |
| 2 | `operating_margin` | 영업이익률 | 매출 대비 영업이익 비율 | PRIMARY | `operating_margin` | `operating_income`, `revenue` |
| 3 | `net_margin` | 순이익률 | 매출 대비 순이익 비율 | PRIMARY | `net_margin` | `net_income`, `revenue` |
| 4 | `free_cash_flow` | FCF | 영업현금흐름에서 자본적지출을 반영한 현금 | PRIMARY | `free_cash_flow` | `operating_cash_flow`, `capital_expenditure` |
| 5 | `net_debt` | 순차입금 | 총차입금에서 현금성 자산을 차감한 금액 | PRIMARY | `net_debt` | `total_debt`, `cash_and_short_term_investments` |

---

## 메트릭 처리 흐름

```
BiMaterializationRequest
        │
        ▼
[BiDocumentProfiler]     ← LLM이 문서에서 기간 목록 추출 (FY, LTM, ...)
        │
        ▼
[build_question_batch]   ← Source 메트릭 × 기간 수 = N개 질문 생성
        │
        ▼
[bi-question worker]     ← 질문별 RAG + LLM 병렬 처리 (K8s Pod 스케일아웃)
        │
        ▼
[snapshot_builder]       ← Derived 메트릭 수식 계산 → BiDashboardSnapshot 발행
```

> **질문 수 계산**: Source 메트릭 **13개** × 기간 수 = 총 질문 수
> (예: 기간이 16개이면 13 × 16 = **208개** 질문)

---

## 부호 정책 (SignPolicy)

| 정책 | 설명 | 적용 메트릭 |
|------|------|-----------|
| `AS_REPORTED` | 문서에 기재된 부호 그대로 사용 | 대부분의 메트릭 |
| `OUTFLOW_NEGATIVE` | 현금 유출이면 음수로 정규화 | CapEx |
| `PERCENT_POINT` | 퍼센트포인트 단위 처리 | (현재 미사용) |
