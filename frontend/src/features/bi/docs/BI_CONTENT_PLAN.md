# BI 내용 및 지표 구현 계획서

## 1. 문서 역할

이 문서는 업로드 및 인덱싱이 끝난 기업 파일에서 BI 지표를 추출하고, 검증하고, 파생 지표를 계산해 버전 스냅샷으로 저장하는 구현 기준이다. 화면 표현은 [BI_DESIGN_PLAN.md](./BI_DESIGN_PLAN.md), API와 프론트 연결은 [BI_INTEGRATION_PLAN.md](./BI_INTEGRATION_PLAN.md)를 따른다.

- 구현 순서: 디자인 완료 후 2순위
- 주요 구현 범위: `backend/modules`, `backend/bi`, `backend/storage`, `backend/api`, `data/workflows`
- 데이터 기준: 한 파일이 한 기업을 나타낸다.
- 기업명 기준: 업로드 시 사용자가 입력한 이름을 사용한다.
- 버전 기준: `workbook_hash`가 파일 버전을 식별한다.
- 제외 범위: 기업 비교, 투자 판단, 예측, 고급 비율 분석, 자유형 답변을 그대로 차트 데이터로 사용하기

## 2. 현재 코드 기준선과 필요한 변경

2026-08-18 현재 확인한 구조는 다음과 같다.

- 인덱싱 워크플로에는 파일 선택, 구조 감지, 셀 직렬화, 임베딩, 벡터 인덱스 저장 모듈이 있다.
- 질의 워크플로에는 Query Input, Decomposer, BM25, Dense, RRF, Context Expander, Reader가 있다.
- `CellTextDocumentDTO`는 `cell_id`, `sheet_name`, `cell_coord`, 행 헤더, 열 헤더, 표시 값을 보존한다.
- Context Expander는 실제 `cell_id`가 들어간 행 단위 컨텍스트를 Reader에 전달한다.
- 현재 `AnswerDTO`는 자유형 `answer: string` 중심이어서 BI 숫자 계약으로 사용할 수 없다.
- LLM 클라이언트는 JSON Schema 기반 구조화 출력을 지원한다.
- 저장소에는 실제 업로드 파일이 없고 API에도 업로드 엔드포인트가 없다.

따라서 기존 Reader 답변을 정규식으로 파싱하지 않는다. 기존 검색 파이프라인은 재사용하되 BI 전용 구조화 Reader, 검증 및 계산 계층, 스냅샷 저장소를 추가한다. `WorkflowExecutor`에는 지표 계산이나 필드 변환 로직을 넣지 않는다.

## 3. V1 기본 카드와 지표

### 3.1 매출 및 성장

| 지표 ID | 표시명 | 종류 | 대표 표시 |
|---|---|---|---|
| `revenue` | 매출 | 원천 | 금액 |
| `revenue_yoy_growth` | 매출 성장률 | 계산 | % |

### 3.2 수익성

| 지표 ID | 표시명 | 종류 | 대표 표시 |
|---|---|---|---|
| `operating_income` | 영업이익 | 원천 | 금액 |
| `operating_margin` | 영업이익률 | 계산 | % |
| `net_income` | 순이익 | 원천 | 금액 |
| `net_margin` | 순이익률 | 계산 | % |

### 3.3 현금흐름

| 지표 ID | 표시명 | 종류 | 대표 표시 |
|---|---|---|---|
| `operating_cash_flow` | 영업현금흐름 | 원천 | 금액 |
| `capital_expenditure` | CapEx | 원천, 부호 정규화 | 금액 |
| `free_cash_flow` | FCF | 계산 | 금액 |

### 3.4 재무 안정성

| 지표 ID | 표시명 | 종류 | 대표 표시 |
|---|---|---|---|
| `cash_and_short_term_investments` | 현금 및 단기투자자산 | 원천 | 금액 |
| `short_term_debt` | 단기차입금 | 원천 보조 | 금액 |
| `current_portion_of_long_term_debt` | 유동성 장기부채 | 원천 보조 | 금액 |
| `long_term_debt` | 장기차입금 | 원천 보조 | 금액 |
| `total_debt` | 총차입금 | 원천 우선, 계산 대체 | 금액 |
| `net_debt` | 순차입금 | 계산 | 금액 |

### 3.5 재무 규모

| 지표 ID | 표시명 | 종류 | 대표 표시 |
|---|---|---|---|
| `total_assets` | 총자산 | 원천 | 금액 |
| `total_liabilities` | 총부채 | 원천 | 금액 |
| `total_equity` | 총자본 | 원천 | 금액 |

원천 보조 지표는 기본 카드의 독립 수치로 노출하지 않지만 총차입금 계산과 근거 확인에 사용한다.

## 4. 기간과 대표값 정책

고정된 연도 수를 가정하지 않는다.

- FY와 LTM을 서로 다른 기간 종류로 저장한다.
- 기본 추세는 최신 FY 5개다.
- FY가 5개보다 적으면 존재하는 FY를 모두 사용한다.
- 사용자는 `최근 3개`, `최근 5개`, `전체`를 선택할 수 있다.
- 대표값은 LTM이 있으면 LTM, 없으면 가장 최근 FY다.
- LTM이 FY0과 같은 종료일 및 같은 값을 나타내면 차트에서 중복 표시하지 않는다.
- 원본에 연도 대신 FY0, FY-1 같은 상대 표기만 있으면 그 표기와 순서를 보존한다.

기간 DTO는 최소한 다음 의미를 가져야 한다.

```json
{
  "period_id": "stable-id",
  "kind": "fy",
  "label": "FY2025",
  "source_label": "FY0",
  "end_date": "2025-12-31",
  "ordinal": 0
}
```

`end_date`를 확정할 수 없으면 `null`로 두고, `ordinal`과 원본 라벨로 정렬한다. 불확실한 날짜를 추정해 채우지 않는다.

## 5. 단위와 값 정책

- 금액은 통화와 배율을 분리해 저장한다. 예: `USD`, `millions`.
- 원본 단위를 확정할 수 없으면 값을 임의 환산하지 않고 `ambiguous`로 처리한다.
- 화면용 축약은 프론트에서 할 수 있지만 계산은 정규화된 백엔드 값을 사용한다.
- `NA`, `NM`, 빈 셀, `null`을 숫자 0으로 바꾸지 않는다.
- 음수는 회계 표시인 괄호와 명시적 부호를 모두 파싱할 수 있어야 한다.
- 퍼센트는 원본 12.3%를 정규화 값 `12.3`으로 저장할지 `0.123`으로 저장할지 한 규칙만 선택한다. V1 계약은 퍼센트 포인트 값 `12.3`을 사용한다.
- 내부 계산에는 `Decimal`을 사용하고 JSON 직렬화 시 정밀도를 잃지 않는 문자열 또는 검증된 숫자 정책을 사용한다.

## 6. 파생 지표 계산 규칙

LLM은 다음 계산을 수행하지 않는다. LLM은 원천 값과 근거만 구조화해 반환하고, 백엔드 materializer가 계산한다.

### 6.1 매출 성장률

```text
revenue_yoy_growth(t) = ((revenue(t) / revenue(t-1)) - 1) * 100
```

- 현재 및 직전 FY가 모두 있어야 한다.
- 직전 매출이 0이면 `not_meaningful`이다.
- LTM 성장률은 비교 가능한 직전 LTM이 없는 한 계산하지 않는다.

### 6.2 영업이익률

```text
operating_margin(t) = operating_income(t) / revenue(t) * 100
```

매출이 0이면 `not_meaningful`이다.

### 6.3 순이익률

```text
net_margin(t) = net_income(t) / revenue(t) * 100
```

매출이 0이면 `not_meaningful`이다.

### 6.4 FCF

```text
free_cash_flow(t) = operating_cash_flow(t) + normalized_capex(t)
```

- `normalized_capex`는 현금 유출을 음수로 저장한다.
- 원본 CapEx가 이미 음수이면 다시 부호를 뒤집지 않는다.
- 원본이 양수 절대값인지 양수 유입인지 문맥으로 확정되지 않으면 계산하지 않고 `ambiguous`로 남긴다.

### 6.5 총차입금

원본에 중복 없는 직접 `total_debt` 값이 있으면 그 값을 우선한다. 직접 값이 없을 때만 다음을 계산한다.

```text
total_debt(t) = short_term_debt(t)
              + current_portion_of_long_term_debt(t)
              + long_term_debt(t)
```

직접 총차입금과 구성 항목을 동시에 더하지 않는다. 구성 항목의 포함 관계가 모호하면 `ambiguous`로 처리한다.

### 6.6 순차입금

```text
net_debt(t) = total_debt(t) - cash_and_short_term_investments(t)
```

현금이 총차입금보다 많으면 음수가 될 수 있으며 정상 값으로 보존한다.

### 6.7 회계식 검증

```text
total_assets(t) ≈ total_liabilities(t) + total_equity(t)
```

허용 오차를 벗어나면 경고를 남기되 원천 값을 자동 수정하지 않는다. 배율 차이가 의심되면 스냅샷을 `partial` 또는 해당 값을 `ambiguous`로 처리한다.

## 7. 지표 카탈로그

지표명과 질문을 코드에 흩어 놓지 않는다. 버전이 있는 지표 카탈로그를 만든다.

각 원천 지표 정의에는 다음을 포함한다.

- `metric_id`
- 한국어 표시명과 쉬운 설명
- 한국어 및 영어 별칭
- 권장 재무제표 및 행 헤더 힌트
- 값 종류: 금액 또는 퍼센트
- 기대 단위 종류
- 부호 정책
- 직접 값과 구성 값의 우선순위
- 제외해야 할 유사 지표
- RAG 질문 템플릿

정규화는 Unicode NFKC, 대소문자 정리, 공백과 문장부호 정리를 기본으로 한다. 부분 문자열만으로 지표를 확정하지 않고 시트, 행 헤더, 열 헤더 문맥을 함께 사용한다.

카탈로그와 계산식에는 별도 `catalog_version`, `formula_version`을 부여한다. 버전이 바뀌면 같은 파일도 새 스냅샷을 만들 수 있어야 한다.

## 8. 추출 파이프라인

### 8.1 전제 입력

업로드 기능 자체는 BI V1 범위 밖이다. 데이터 소스 또는 업로드 단계가 다음 값을 BI materialization에 전달해야 한다.

- `company_id`
- 사용자가 입력한 `display_name`
- `file_name`
- `workbook_hash`
- 인덱싱 완료를 가리키는 문서 및 인덱스 참조

한 기업의 새 파일은 같은 `company_id`와 새로운 `workbook_hash`를 사용한다.

### 8.2 문서 프로파일링

파일당 한 번 구조화 질의를 수행해 다음을 찾는다.

- 사용 가능한 FY 및 LTM 기간
- 통화와 배율
- 관련 시트 후보
- 기간 라벨과 종료일

프로파일 결과도 cell evidence를 포함하고 Pydantic DTO로 검증한다. 발견되지 않은 정보는 추정하지 않는다.

### 8.3 원천 지표 추출

발견한 각 `원천 지표 x 기간` 조합을 하나의 원자적 요청으로 처리한다.

질문 템플릿의 의미는 다음과 같다.

```text
이 문서에서 {period_label}의 {metric_label} 값을 찾아라.
계산하지 말고 원문 값, 통화, 배율, 근거 cell_id를 구조화해 반환하라.
찾지 못했거나 후보가 충돌하면 그 상태를 반환하라.
```

각 요청은 기존 BM25, Dense, RRF, Context Expander를 통과한다. 자유형 Reader 대신 BI 전용 구조화 Reader를 사용한다.

### 8.4 구조화 출력

관측값은 최소한 다음 정보를 가진다.

```json
{
  "request_id": "request-id",
  "metric_id": "revenue",
  "period_id": "period-id",
  "status": "available",
  "raw_value": "1,234.5",
  "normalized_value": "1234.5",
  "currency": "USD",
  "scale": "millions",
  "evidence": [
    {
      "cell_id": "sheet-code:B12",
      "sheet_name": "Income_Statement",
      "cell_coord": "B12",
      "source_text": "FY2025: 1,234.5"
    }
  ],
  "notes": []
}
```

`status`는 `available`, `missing`, `ambiguous`, `invalid`, `not_meaningful`의 닫힌 집합으로 둔다. 선언되지 않은 필드는 거부한다.

### 8.5 검증

구조화 출력 뒤에 다음을 검사한다.

1. 요청한 `metric_id`와 `period_id`인지 확인
2. 숫자 형식과 회계 음수 형식 확인
3. evidence의 `cell_id`가 실제 Context에 존재하는지 확인
4. 시트와 셀 위치가 문서 계보와 일치하는지 확인
5. 같은 시리즈의 통화와 배율 일관성 확인
6. 직접 값과 구성 값의 중복 및 충돌 확인
7. `NA`, `NM`, `null` 상태 보존 확인
8. 계산 전 필요한 입력이 모두 있는지 확인

충돌을 임의로 평균 내거나 첫 번째 값으로 확정하지 않는다.

## 9. 스냅샷과 상태

BI 화면은 페이지 로드 때 RAG를 호출하지 않는다. materialization이 만든 스냅샷만 읽는다.

### 9.1 상태

- `queued`
- `indexing`
- `profiling`
- `extracting`
- `materializing`
- `ready`
- `partial`
- `failed`

`ready`와 `partial`은 게시 가능한 성공 상태다. `failed`는 게시하지 않는다.

### 9.2 게시 규칙

- 최초 파일이면 성공 스냅샷이 생길 때까지 처리 상태를 보여준다.
- 같은 기업의 새 파일 처리 중에는 현재 게시된 스냅샷을 계속 제공한다.
- 새 작업이 `ready` 또는 `partial`이 되면 `current_snapshot_id`를 원자적으로 교체한다.
- 새 작업이 실패하면 기존 `current_snapshot_id`를 유지한다.
- 스냅샷은 `company_id`, `workbook_hash`, 카탈로그 버전, 계산식 버전으로 추적한다.

### 9.3 저장소

현재 프로젝트의 파일 기반 저장 방식에 맞춰 V1은 `data/artifacts/bi/` 아래 JSON 아티팩트를 사용한다.

```text
data/artifacts/bi/
├── companies.json
├── jobs/<job_id>.json
└── snapshots/<company_id>/<snapshot_id>.json
```

임시 파일에 완성된 JSON을 쓴 뒤 원자적 replace로 교체한다. API 요청에서 파일 시스템 경로를 직접 받지 않는다. 향후 인증 및 다중 사용자 환경에서는 DB 저장소로 교체할 수 있도록 storage Protocol 경계를 둔다.

## 10. 권장 백엔드 구조

```text
backend/
├── bi/
│   ├── __init__.py
│   ├── models.py
│   ├── catalog.py
│   ├── calculator.py
│   └── materializer.py
├── modules/
│   ├── bi_document_profiler.py
│   └── bi_metric_reader.py
├── storage/
│   └── bi_snapshot.py
└── api/
    └── bi_routes.py

data/workflows/
└── bi_materialization.json
```

- `backend/bi/models.py`: 회사, 기간, 관측값, 지표 시리즈, 스냅샷, 작업 상태 DTO
- `backend/bi/catalog.py`: 지표 별칭, 소스 우선순위, 질문 템플릿, 버전
- `backend/bi/calculator.py`: 순수 `Decimal` 계산과 상태 전파
- `backend/bi/materializer.py`: 원자적 요청 생성, 워크플로 실행 조정, 결과 수집, 게시
- `bi_document_profiler.py`: 기간, 단위, 시트 프로파일 구조화 추출
- `bi_metric_reader.py`: Context와 지표 요청을 받아 구조화 관측값 출력
- `bi_snapshot.py`: 회사, 작업, 스냅샷 저장과 원자적 현재 버전 교체
- `bi_routes.py`: materialization 시작, 상태 조회, 회사 및 현재 스냅샷 조회

새 `backend/bi` 패키지를 추가하면 `docs/backend_module_architecture.md`의 패키지 책임 표도 갱신한다. 모듈 계약을 추가한 뒤 `backend/modules/docs/`의 Markdown을 재생성한다.

## 11. 캐시와 비용 제어

- 원자적 추출 캐시 키: `workbook_hash + catalog_version + metric_id + period_id + retrieval_config + reader_version`
- 성공한 관측값은 같은 키에서 재사용한다.
- 실패나 모호한 결과의 영구 캐시는 짧은 정책 또는 명시적 재실행을 사용한다.
- 동시 LLM 호출 수를 제한한다.
- 작업 상태에 전체 요청 수, 완료 수, 실패 수, 토큰 및 비용 합계를 기록한다.
- 정확도가 확인되기 전에는 여러 기간을 한 자유형 답변으로 묶어 비용만 줄이지 않는다.

## 12. 외부 데이터 전송 안전 조건

현재 구조의 LLM 및 임베딩 provider가 외부 API를 사용하면 업로드된 재무 셀과 질문 컨텍스트가 외부 서비스로 전송될 수 있다.

- 실제 외부 API 호출을 활성화하기 전에 전송되는 데이터와 provider를 사용자에게 설명하고 승인을 받아야 한다.
- 디자인 fixture, 계산 단위 테스트, 저장소 테스트는 외부 API 없이 수행한다.
- 자동 테스트에서는 fake completion client와 deterministic embedding을 사용한다.
- 로그와 오류 응답에는 원본 재무 셀 전체를 남기지 않는다.

## 13. 구현 순서

1. 공통 DTO, 상태 집합, 지표 카탈로그 버전을 정의한다.
2. `bi_document_profiler`와 `bi_metric_reader`의 독립 실행 계약을 만든다.
3. fake completion client로 구조화 출력과 evidence 검증을 테스트한다.
4. `Decimal` 기반 계산기와 상태 전파를 구현한다.
5. 파일 기반 스냅샷 저장소와 원자적 게시를 구현한다.
6. 기존 검색 모듈과 BI 모듈을 연결한 materialization 워크플로를 만든다.
7. materializer가 원천 지표 x 기간 요청을 생성하고 결과를 모으게 한다.
8. 새 파일 성공, 부분 성공, 실패의 버전 교체 규칙을 테스트한다.
9. BI API 라우트를 추가하고 OpenAPI 및 모듈 문서를 갱신한다.
10. 외부 API 승인을 받은 경우에만 실제 파일로 제한된 통합 실행을 수행한다.

## 14. 검증 시나리오

- FY가 2개뿐인 파일에서 두 기간만 저장한다.
- FY 5개 이상인 파일에서 전체 기간을 저장하고 기본 조회는 최신 5개가 된다.
- LTM이 있는 파일과 없는 파일에서 대표값이 올바르게 선택된다.
- LTM과 FY0이 같은 기간이면 중복 표시용 관측값을 만들지 않는다.
- `NA`, `NM`, 빈 셀은 0이 되지 않는다.
- 매출 또는 영업이익이 없으면 영업이익률이 계산되지 않는다.
- 직전 매출 0이면 성장률이 `not_meaningful`이다.
- 양수 절대 CapEx와 음수 CapEx에서 FCF 부호가 정확하다.
- 직접 총차입금과 구성 항목이 함께 있을 때 이중 합산하지 않는다.
- 근거 없는 숫자와 Context에 없는 cell ID는 `invalid`로 거부한다.
- 일부 지표가 없어도 `partial` 스냅샷을 게시한다.
- 새 버전 실패 시 이전 스냅샷이 계속 현재 버전이다.
- 같은 해시와 같은 카탈로그 버전 재실행은 캐시를 사용한다.
- `python -m unittest discover -s tests`가 외부 API 없이 성공한다.
- `python -m backend.tools.generate_module_docs` 후 체크인 문서가 계약과 일치한다.

## 15. 내용 구현 완료 조건

- 5개 카드에 필요한 모든 원천 및 파생 지표가 ID와 공식으로 정의돼 있다.
- 자유형 `AnswerDTO.answer` 파싱 없이 구조화 DTO로 값과 근거를 받는다.
- 모든 파생 계산이 백엔드에서 결정적으로 수행된다.
- 기간, 단위, 결측, 모호성, evidence 검증이 구현돼 있다.
- BI 페이지 로드가 RAG를 다시 실행하지 않고 게시된 스냅샷을 읽는다.
- 같은 기업의 재업로드가 성공하기 전까지 이전 BI를 보존한다.
- 외부 API 없이 단위 및 통합 테스트가 가능하다.

