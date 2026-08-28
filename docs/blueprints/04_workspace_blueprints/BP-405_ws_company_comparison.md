# [BP-405] Company Comparison & Financial League 대시보드 청사진
> **Document Code:** `BP-405` | **Category:** Workspace Blueprint | **Status:** Active Production Feature  
> **Source Files:** [`backend/features/company_comparison/`](file:///c:/Repos/bist-mini-final/backend/features/company_comparison/), [`backend/features/company_comparison/league_scoring.py`](file:///c:/Repos/bist-mini-final/backend/features/company_comparison/league_scoring.py), [`frontend/src/pages/CompanyComparisonPage.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/pages/CompanyComparisonPage.tsx), [`frontend/src/pages/CompanyComparisonV2Page.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/pages/CompanyComparisonV2Page.tsx), [`frontend/src/features/company-comparison-v2/`](file:///c:/Repos/bist-mini-final/frontend/src/features/company-comparison-v2/)

---

## 1. 기업 비교 및 파이낸셜 리그 아키텍처 (Cross-Company Comparison Architecture)

**Company Comparison Dashboard**는 2개 이상의 복수 기업(예: IBM, 비스텔리젼스, 콜드플레이, DH 이노베이션)을 선택하여 **수익성, 안정성, 성장성, 활동성 지표를 동일 회계 기준/통화 단위로 정규화하여 크로스 비교하고 듀퐁 3단계 분해 트리 및 파이낸셜 리그 테이블을 시각화**하는 분석 워크스페이스입니다.

```mermaid
flowchart TD
    subgraph MultiCompanySelection ["1. 다중 기업 및 리그 조회"]
        COMP_REQ["비교 요청 (Base vs Target / 전체 리그)"]
    end

    subgraph BackendComparisonEngine ["2. 백엔드 지표 정규화 및 계산 엔진"]
        LEAGUE_SVC["FinancialLeagueService (리그 데이터 조립)"]
        LEAGUE_SCORE["league_scoring (성장성 35% + 수익성 35% + 안정성 30%)"]
        COMP_SVC["CompanyComparisonService (듀퐁 & 델타 계산)"]
        CALC["DuPontCalculator (ROE 3단계 무손실 연산)"]
        CACHE["ComparisonCache (인메모리 캐시)"]
        LEAGUE_SVC --> LEAGUE_SCORE
        COMP_SVC --> CALC
        COMP_SVC --> CACHE
    end

    subgraph FrontendVisualizers ["3. 크로스 비교 시각화 컴포넌트"]
        LEAGUE_PAGE["CompanyComparisonV2Page (선택·정렬·화면 조립)"]
        METRIC_RANK["metricRanking (지표별 순위 정책)"]
        ANALYSIS["leagueAnalysis (순위 사유·추이 계산)"]
        CHARTS["LeagueCharts (추이·포지션 차트)"]
        DUPONT_TREE["DuPontTree (ROE = 순이익률 x 자산회전율 x 레버리지)"]
        RADAR["RadarChart (5각 재무 건전성 방사형 차트)"]
        LEAGUE_PAGE --> METRIC_RANK
        LEAGUE_PAGE --> ANALYSIS
        LEAGUE_PAGE --> CHARTS
    end

    MultiCompanySelection --> BackendComparisonEngine
    BackendComparisonEngine --> FrontendVisualizers
```

---

## 2. 듀퐁 분석(DuPont Analysis) 분해 모델 및 수식

기업 간 ROE(자기자본이익률) 격차의 근본 원인을 분석하기 위해 3단계 듀퐁 분해 공식을 적용합니다:

$$
\text{ROE} = \underbrace{\left(\frac{\text{당기순이익}}{\text{매출액}}\right)}_{\text{순이익률 (Profit Margin)}} \times \underbrace{\left(\frac{\text{매출액}}{\text{총자산}}\right)}_{\text{총자산회전율 (Asset Turnover)}} \times \underbrace{\left(\frac{\text{총자산}}{\text{자기자본}}\right)}_{\text{재무레버리지 (Financial Leverage)}}
$$

---

## 3. REST API 규격

### ① `GET /api/v1/company-comparisons/league`
- **역할**: 파싱된 기준 기업과 비교용 재무 시나리오 기업의 성장성·수익성·안정성 종합 점수 및 리그 순위 반환.
- **반환 DTO**: `FinancialLeagueResponse(schema_version, generated_at, historical_end_year, companies, spotlight, evidence)`
- **점수 정책**: 성장성 35%, 수익성 35%, 안정성 30%의 고정 절대 벤치마크를 사용하므로 기업 추가·제거가 개별 점수 자체를 바꾸지 않습니다.

### ② `POST /api/v1/company-comparisons/analyze`
- **역할**: Base 기업과 Target 기업 간의 듀퐁 3단계 분해, 5각 레이더 지표 및 전년 대비 증감률(Delta) 비교.
- **요청 Body**: `CompanyComparisonRequest(base_company_id, target_company_id, fiscal_year)`
- **반환 DTO**: `CompanyComparisonResponse(dupont_breakdown, radar_metrics, summary_delta)`

---

## 4. 프론트엔드 구현 컴포넌트
- [`CompanyComparisonPage.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/pages/CompanyComparisonPage.tsx): 듀퐁 3단계 분해 트리 및 2개 기업 직접 비교 뷰.
- [`CompanyComparisonV2Page.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/pages/CompanyComparisonV2Page.tsx): 파이낸셜 리그 화면 조립, 기업 선택 및 2개 기업 비교 상태 관리.
- [`metricRanking.ts`](file:///c:/Repos/bist-mini-final/frontend/src/features/company-comparison-v2/metricRanking.ts): 종합·매출·영업이익·성장률·이익률별 순위와 표시 방향 정책.
- [`leagueAnalysis.ts`](file:///c:/Repos/bist-mini-final/frontend/src/features/company-comparison-v2/leagueAnalysis.ts): 순위 사유, 평가축 기여도, 과거 추이와 평균 대비 계산.
- [`LeagueCharts.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/features/company-comparison-v2/LeagueCharts.tsx): 단일/비교 추이 차트와 성장성×수익성 포지션 마커.
- [`CompanyLogoBadge.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/features/company-comparison-v2/CompanyLogoBadge.tsx): 기업별 로고 배지 렌더링.

리그의 기업명 링크는 `/dashboard?companyId={id}`로 이동합니다. BI 화면의 `useSelectedBiCompany` 훅이 URL과 브라우저 탐색 이벤트를 동기화하므로 기업비교 API와 BI API의 namespace는 분리된 상태로 화면 간 선택 문맥만 전달됩니다.
