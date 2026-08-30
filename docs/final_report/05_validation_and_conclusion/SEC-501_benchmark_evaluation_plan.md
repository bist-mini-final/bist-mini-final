# [SEC-501] 품질 평가 계획과 기준
> **Chapter:** 5. 품질 검증 및 결론 | **Section:** 5.1 | **Status:** Current Plan

---

## 1. 검증 층위

| 층위 | 대상 | 판정 기준 |
| :--- | :--- | :--- |
| Static | architecture import, lint, Python/TS type | 위반·오류 0건 |
| Contract | Pydantic/Zod DTO, OpenAPI, Alembic, K8s renderer | schema/route/migration drift 0건 |
| Unit | BI 수식, comparison 점수·순위·예측, module pin | 결정론적 기대값 일치 |
| Integration | PostgreSQL queue/lease/SSE, Redis signal, snapshot publish | 상태 전이와 복구 계약 일치 |
| Frontend | route, hook, schema, rendering state | ready/loading/error/empty 상태 회귀 없음 |
| Benchmark | RAG answer/evidence/latency | dataset별 측정값과 release threshold 기록 |

---

## 2. RAG benchmark

`BenchmarkService`는 benchmark set의 workflow/case를 durable job으로 실행하고 `benchmark_result_rows`에 case 결과를 저장합니다. 핵심 지표는 answer accuracy, evidence precision/recall, latency, failed case 수입니다.

목표값은 제품 방향을 위한 release gate 후보이며 측정 결과처럼 표현하지 않습니다.

- 숫자·단위 exact match 목표: 95% 이상
- source cell Recall@5 목표: 98% 이상
- hallucinated/unsupported numeric claim 목표: 0%
- latency 목표: 실행 환경과 workflow profile별로 별도 설정

외부 OpenAI 호출이 필요한 end-to-end benchmark는 비용·rate limit·model 변화가 있으므로 결정론적 기본 CI와 분리하고 실행 환경, model ID, dataset version, 측정 시각을 결과에 남깁니다.

---

## 3. Company Comparison 평가

1. 입력 기업은 current BI snapshot과 일치해야 합니다.
2. 사용 금액은 같은 통화·배율이고 최신 재무상태 값은 비교 최신 FY와 일치해야 합니다.
3. 모든 actual period와 balance-sheet 입력은 snapshot 내부 evidence ID로 해석돼야 합니다.
4. 점수는 `financial-league-v3`의 고정 기준으로 재현돼야 합니다.
5. 동점은 competition rank로 처리돼야 합니다.
6. 예측은 정확히 3개년, `historical-cagr-hold-v1`, CAGR -12%~30% 제한, 최신 margin 유지 조건을 따라야 합니다.
7. 예측은 composite score에 영향을 주면 안 됩니다.
8. 원천 fingerprint가 같으면 같은 snapshot identity를 재사용하고, 달라지면 새 이력을 발행해야 합니다.
9. 근거가 불완전한 기업은 제외되며 2개 미만이면 409여야 합니다.

---

## 4. 릴리즈 증적

각 릴리즈에서는 command, commit, 실행 환경, test count, skipped 사유, migration head, smoke-test 대상 API를 함께 기록합니다. “0% 오류”, “몇 % 비용 절감” 같은 주장은 실제 측정 artifact가 없으면 결론에 포함하지 않습니다.
