# Company Comparison Snapshot 설계 결정

## 결정

- 기존 `/company-comparison`의 legacy 직접 계산 구현과 `/company-comparison-v2` 라우트를 제거한다.
- V2의 재무 순위·선택 비교 UX를 `/company-comparison`의 정식 화면으로 사용한다.
- 기업 비교는 BI API와 분리된 `/api/v1/company-comparisons` namespace를 유지한다.
- BI가 발행한 기업별 스냅샷은 읽기 전용 원천으로 사용한다.
- 비교 계산 결과는 별도의 `CompanyComparisonSnapshot`으로 PostgreSQL에 발행한다.
- 공통화는 버전형 스냅샷 저장·현재 head 전환에 한정한다. BI 계산과 비교 점수 정책은 합치지 않는다.

## API

| Method | Path | 설명 |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company-comparisons/snapshot` | 현재 비교 스냅샷 조회 |
| `POST` | `/api/v1/company-comparisons/snapshot/refresh` | 최신 BI 원천으로 비교 스냅샷 검증·발행 |

## 무결성 정책

- 매출·영업이익 공통 FY가 2개 이상이어야 한다.
- 총부채·총자산·순부채는 비교 최신 FY와 동일한 연도·통화·배율이어야 하고, 사용 관측값에 원본 셀 근거가 있어야 한다.
- 누락 연도, 부채율, 마진을 임의로 보간하지 않는다.
- 조건을 충족하지 못한 기업은 `exclusions`에 사유를 기록한다.
- 검증 기업이 2개 미만이면 `409`로 발행을 거부한다.
- 향후 3개년 예측은 버전형 가정으로 표시하고 종합 점수에는 사용하지 않는다.

상세 계약은 [`BP-405`](file:///c:/Repos/bist-mini-final/docs/blueprints/04_workspace_blueprints/BP-405_ws_company_comparison.md)를 기준으로 한다.
