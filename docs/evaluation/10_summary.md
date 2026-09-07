# Excel RAG 서버 실측평가 최종 보고서

평가일은 2026-09-01 KST다. 전달 패키지의 배포·데이터·정적 시험·RAG 품질·부하·복구·보안 항목을 실행하고, 발견 결함을 개선한 최신 dirty 이미지를 재빌드·재배포해 후속 검증했다.

## 최종 판정

**학생 기업 주제 프로젝트 목표 범위 통과 / 정제 직접 조회 RAG 평가 완료**

- 애플리케이션 배포, 4개 워크북 무결성·색인, 자동시험, 418 run 기준선, 제한된 사후 개선 160 run, 읽기/RAG 부하, 일부 장애복구, 업로드·명세·헤더·rate limit 검증은 완료했다.
- 기준선과 사후 개선 진단을 보존한 채, 질문·기업·FEATURE를 정제한 직접 조회형 124문항을 `rag_query` 단일 workflow로 실행했다. 124/124 완료, Answer 94/124(75.81%), 실행 오류 0건이다.
- 209문항을 workbook FEATURE·시트·기간 기준으로 전수검사해 93문항을 수정하고 5문항을 프로젝트 범위에서 제외했다. 평가 범위 204건 중 자동 직접 셀 채점이 가능한 124문항을 최종 실행했고, 나머지 80건은 별도 계산·판단 scorer 대상으로 분리했다.
- 서명 세션 인증, PBKDF2 credential, viewer/operator/admin RBAC와 단일 tenant 경계를 구현·재배포해 실측 통과했다. 외부 공인 TLS는 DNS·공유기·인증서 권한이 필요해 대기 중이다.
- 공인 TLS, 전체 `expected_plan` 수동 gold, 유효 500MiB 전체 적재, ingestion worker 강제 종료, signed release는 상용 운영 범위이므로 본 학생 프로젝트 수용 기준에서 제외한다. 실제 PostgreSQL 중단·복구는 통과했다.

## 전달 체크리스트

| 요청 항목 | 상태 | 비고 |
| --- | --- | --- |
| commit·image digest·migration | 완료 | dirty fingerprint 포함, clean release는 아님 |
| 실행 환경 | 완료 | `00_environment.md` |
| 4개 Excel 적재·무결성 | 완료 | 4/4 completed, 45,120 vector, stale 0 |
| 자동시험·정적 분석·frontend build | 완료 | pytest 379 pass/2 skip, Ruff/Pyright/frontend pass |
| 1차 86, 2차-A 87, 2차-B 36 | 완료 | 418 run, cache off |
| 2차 전체 123 집계 | 완료 | 동일 기준선 환경 |
| route·plan·sheet·answer·evidence·운영 효율 | 완료(프로젝트 범위) | Plan은 수동 gold 제외로 N/A |
| 유형·오류·대표 실패 | 완료 | 정제 124 run 및 단계별 실패 분석 완료 |
| 읽기·RAG·upload·SSE·queue 부하 | 완료(프로젝트 범위) | 유효 500MiB 전체 ingestion은 상용 운영 범위 제외 |
| Worker·Redis·DB·migration·API 복구 | 완료(프로젝트 범위) | ingestion worker 강제 종료는 상용 운영 범위 제외 |
| 보안 | 완료(프로젝트 범위) | auth/RBAC/단일 tenant 통과, 공인 TLS는 상용 운영 범위 제외 |
| 화면 캡처 | 완료 | dashboard/data sources/jobs |
| 검토자 승인 | 평가 제외 | 조직 QA 서명 절차가 없는 학생 프로젝트 |

## 배포·데이터

| 항목 | 결과 |
| --- | --- |
| Git | `dev` / `38a18ed2...f98a`, `origin/dev` 일치, dirty 66경로(평가 산출물 포함) |
| 전달 기준 | `e74cb5c...148`과 불일치; 이후 최신 코드 평가 |
| 배포 tag | `38a18ed2c1bb-dirty-5a5d1f46011f` |
| Kubernetes | k3d/K3s 1.35.5, node 1, API/frontend/Redis ready; API/frontend restart 0, Redis restart 1(Docker Desktop 재기동 이력) |
| KEDA | 6 ScaledJob ready/inactive; resource-based max 3 |
| DB | PostgreSQL 16.15, pgvector 0.8.6, Alembic `20260901_0009` |
| 모델 | `gpt-5.6-luna`, `text-embedding-3-large` 3,072d |

IBM, 기업 A, Coldplay, DH Innovation의 SHA-256은 전달 기준과 일치하고 각 4개 sheet, 수식 오류 0, BS 회계등식 차이 0이다. vector는 11,592/10,944/12,144/10,440개이며 hash별 활성 index는 하나다.

## 자동시험

| 검사 | 결과 | 판정 |
| --- | --- | --- |
| Backend pytest | 379 passed, 2 skipped, 1 deprecation warning | 통과 |
| Ruff | all checks passed | 통과 |
| Pyright | 0 errors/warnings | 통과 |
| Frontend | lint/typecheck, 51 files·181 tests, production build | 통과 |
| Helm / shell | lint 1 chart·0 failure, template 성공, `local.sh` syntax 성공 | 통과 |

## RAG 기준선 품질

| 평가 대상 | 사례/run | Answer | Route | Plan | Sheet exact | Evidence Hit@k | Recall@k | Citation | 오류율 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1차 포함 | 86 / 172 | 29.07% | 55.04% | N/A | 56.59% | 46.91% | 42.92% | 21.66% | 25.00% |
| 2차-A IBM | 87 / 174 | 57.47% | 75.00% | N/A | 75.00% | 70.69% | 67.82% | 62.93% | 14.94% |
| 2차-B Holdout | 36 / 72 | 43.06% | 69.70% | N/A | 69.70% | 69.64% | 59.44% | 43.15% | 8.33% |
| 2차 전체 | 123 / 246 | 53.25% | 73.36% | N/A | 73.36% | 70.43% | 65.78% | 58.11% | 13.01% |

| Workflow | run | Answer | Route | Sheet | 평균 지연 | p95 | p99 | 평균 token | 총 비용 | 오류율 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `bi_metric_extraction` | 209 | 44.02% | 66.10% | 66.67% | 12.20s | 36.78s | 51.98s | 25,212 | $0.454973 | 15.31% |
| `rag_query` | 209 | 42.58% | 66.87% | 67.47% | 11.01s | 31.14s | 46.93s | 19,874 | $0.371520 | 20.57% |

골드셋은 canonical JSON 부재로 Markdown에서 재구성됐다. `expected_plan`은 사람 검수 없이 추론하지 않아 0건이며 Plan은 N/A다. 자동 review 418건은 pass 141, fail 251, manual required 26이지만 사람 승인으로 간주하지 않는다.

원시 43.30%에는 기업명이 없는 질문 76 run, catalog 밖 기업 6 run, reference 자동 파싱 불가 26 run과 중복 조건이 포함됐다. 같은 원시 실행을 `기업 명시 + catalog 존재 + gold 파싱 가능`로 제한하면 322 run의 Answer는 52.17%, 그중 직접 원본 셀 조회형 210 run은 65.71%다. 이는 원시 점수를 대체하는 최종 성능이 아니라 평가셋과 실제 RAG 결함을 분리하기 위한 진단값이다.

추가 FEATURE 전수검사에서는 질문·기업 범위 수정 93건을 확인했다. 25건은 `매출` 계열 질문을 `Total Revenue` 계열 셀로 채점하는 의미 불일치였고, `총부채`와 `Total Debt`가 뒤섞인 1건, source sheet·정확한 FEATURE·기간을 명시하지 않은 의미 모호성 43건도 확인했다. 전체 209문항의 원문·수정문·FEATURE·참조·포함 여부는 `05_benchmark_results/evaluation-set-quality-review.md`에 수록했다. 정제 평가에는 204문항을 포함하고 미적재 시트·기업 관련 5문항은 제외한다.

## 정제 직접 조회 최종 평가

정제 평가 중 직접 원본 셀로 자동 채점할 수 있는 124문항을 `rag_query` 하나로
실행했다. 124는 수정 문항 수가 아니라 직접 조회 subset 수이며, workflow를 두 번
실행하지 않았다.

| Answer | Route | Sheet exact | strict Hit@k | strict Recall@k | Citation | 오류율 | 평균 지연 | p95 | 총 비용 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **75.81% (94/124)** | 72.58% | 72.58% | 67.80% | 64.61% | 58.52% | **0%** | 8.358s | 13.806s | **$0.287985** |

30개 자동 오답은 strict gold 셀 검색/융합 미도달 20건, Reader 부분 근거 7건,
Reader 근거 미선택 1건, 검색·근거가 맞지만 답변/채점 의미가 다른 2건으로
분류됐다. 숫자 골드 중복, `전망/추정` 같은 동의어와 지급액의 음수 부호 때문에
실패한 사례까지 포함하면 사람 검토 참고치는 99/124(79.84%)지만, 공식 exact
수치는 75.81%로 보존한다. 상세 내역은
`05_benchmark_results/corrected-direct-rag-query-report.md`에 있다.

## 사후 개선 결과

기준선을 본 뒤 실패 중심 80건×2 Workflow를 재실행했다. 따라서 아래 결과는 post-hoc이며 Holdout이 아니다.

| 구분 | Answer | Sheet | Hit@k | Recall@k | Citation | 오류율 | 평균 지연 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 동일 80건 기준선 | 25.00% | 67.42% | 38.41% | 33.90% | 24.39% | 44.38% | 8.16s |
| 개선 후 | 40.00% | 72.54% | 67.39% | 61.74% | 43.44% | 11.25% | 12.49s |

Decomposer catalog 보정·빈 계획 재시도, Reader 완전성 지시, 다기업 route 채점 개선이 근거 도달률과 오류율을 개선했다. 새 동결 Holdout으로 일반화 여부를 다시 확인해야 한다.

동일 post-hoc 중 유효 직접 조회형 56 run만 비교하면 Answer는 39.29%에서 62.50%로 +23.21%p 개선됐다. 기존 105문항 회귀실행은 145/210(69.05%)·실행 오류 0건이었지만 의미 감사 전 세트이므로 실행 안정성 증거로만 사용한다. 수정 대상 93문항을 제외해 과거 실행을 다시 분류한 의미상 유효 subset 63문항·126 run은 126/126 정답이었다. 실제 제품 로직은 RRF 순위 보존, 명시적 metric·source sheet 보존, 전체 컨텍스트 기반 Reader 근거 선택 1회 복구로 보강했다. 최종 공식 직접 조회 성능은 위 새 124 run의 75.81%이며 과거 subset 수치로 대체하지 않는다.

## 성능·부하

- 읽기 API 정식 5분×4단계: 703,940건, 200 266,046건, 429 437,894건, 5xx/timeout 0건.
- 동시성 1: 6,592/6,592 성공, RPS 21.97, p95 42.65ms.
- 동시성 10/25/50의 429는 Ingress 30 RPS·burst·connection 정책 초과를 정상 차단한 결과다. CPU 포화나 서버 오류는 확인되지 않았다.
- RAG 1/3/5/10 burst: 19/19 완료, 처리량은 동시성 5부터 약 10 run/min, 동시성 10 p95 62.12s.
- 500MiB 경계: 정확한 상한은 크기 통과 후 시그니처 422, +1 byte는 413, Job 생성 0.
- API rolling restart: 개선 후 120초 952건, 실패 0.

## 복구·보안

- Benchmark worker 종료 후 약 225초에 진행 재개, 16/16 완료, 중복 0.
- Redis 중단 시 PostgreSQL fallback으로 SSE 2/2 종료 수신, 중복 0.
- API 2 replica에서 SSE 4/4 종료 수신, 중복 0.
- 잘못된 DB staging API는 ready 되지 않고 fail-fast, migration exit 42는 기존 production을 유지했다.
- API 명세·readiness 외부 노출 차단, CORS, 보안 헤더, rate limit, 업로드 시그니처/크기, Secret/log scan은 통과했다.
- 배포 후 익명 API 401, login 200, 인증 조회 200, tenant 위반 403, logout 200, logout 후 401, 외부 OpenAPI 404를 확인했다. HttpOnly·SameSite=Strict 쿠키를 사용한다.
- 검색 셀의 prompt injection 문자열을 system instruction과 분리하는 회귀 시험과 셀 좌표 traversal 거부 시험도 통과했다.
- PostgreSQL container 중단 시 readiness 503, 재시작·healthy 후 200 자동 복구를 확인했다.
- 외부 HTTP는 접근 가능하지만 HTTPS는 아직 연결되지 않아 공개 운영 TLS gate는 대기다.

## 비용

평가 패키지에서 직접 추적되는 비용은 다음과 같다.

| 구분 | 비용 |
| --- | ---: |
| 4개 평가 workbook embedding | $0.317065 |
| 기준선 418 run | $0.826493 |
| 사후 개선 160 run | $0.316738 |
| 정제 직접 조회 124 run | $0.287985 |
| RAG 동시성 19 run | $0.052281 |
| SSE 검증 2 run | $0.006291 |
| **합계** | **$1.806853** |

읽기 API·업로드 경계·정적 테스트·Kubernetes 장애 검증은 모델 비용이 없다. 이 합계는 평가 패키지에 연결된 실행만 포함하며, 사용자가 별도로 실행한 채팅은 포함하지 않는다.

## 상용 운영 범위에서 제외한 항목

아래 항목은 구현 실패나 미완료가 아니라 학생 기업 주제 프로젝트의 목적·비용·운영 환경을 넘어서는 요구사항이다. 최종 프로젝트 수용 조건과 점수에서 제외한다.

| 제외 항목 | 현재 프로젝트에서 확보한 수준 | 제외 사유 |
| --- | --- | --- | --- |
| 공인 TLS·외부 443·인증서 운영 | Helm TLS Secret·SSL redirect 입력 계약 | 도메인·공유기·공인 인증서가 필요한 상용 인프라 항목 |
| 209건 전체 `expected_plan` 수동 gold·조직 QA 서명 | route/sheet/answer/evidence 자동 지표와 원시 run 보존 | 전담 검토 조직이 필요한 절차 |
| 대규모 독립 Holdout | 기존 Holdout과 post-hoc 결과 분리 | 추가 유료 호출 대신 소규모 미사용 문항만 선택 검증 |
| ingestion shard 강제 종료 | KEDA·lease·재시도 계약 및 benchmark worker 복구 검증 | 유료 재임베딩과 별도 staging 장애 창 필요 |
| 유효 500MiB Excel 전체 적재 | 500MiB/500MiB+1 전송 경계 검증 | 학생 프로젝트 데이터 규모를 벗어나는 비용·자원 시험 |
| signed tag·외부 registry digest·SBOM | Git SHA·dirty fingerprint·로컬 image ID | 상용 공급망·정식 release 관리 항목 |

## 증빙

- 환경·이미지: `00_environment.md`, `01_commit_images_migrations.txt`
- 자동시험: `02_static_tests/`
- 데이터: `03_ingestion_manifest.csv`, `03_workbook_audit.*`
- 요청·골드 감사: `04_benchmark_requests/`
- 품질: `05_benchmark_results/`, `06_case_review.csv`
- 성능: `07_loadtest/`
- 복구: `08_resilience/`
- 보안: `09_security/`
- 개선: `11_remediation.md`
- 화면: `12_screenshots/`
- 재현 명령: `13_execution_log.md`
