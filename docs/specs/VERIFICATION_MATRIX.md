# 검증 매트릭스

| 요구사항 | 자동 검증 | 통합/운영 검증 | 완료 조건 |
| --- | --- | --- | --- |
| MOD-001, JOB-001/002 | registry/job contract test, DAG compile test | 표준 workflow API 조회 | 모든 표준 Job이 포트 오류 없이 compile |
| RUN-001/002 | dispatcher 멱등성, API `202` test | PostgreSQL queue row 확인 | API 프로세스 module execute 0회 |
| RUN-003/004/005 | resume/cancel/SSE disconnect test | Pod 중단·lease recovery | 성공 노드 중복 0, disconnect 후 완료 |
| ING-001~005 | fixture xlsx pipeline contract | kind/k3d + PostgreSQL E2E | source→index→metadata 모두 조회 가능 |
| RAG-001~005 | semantic scope, dense/keyword/RRF tests | seed DB 질의 E2E | 답변과 근거, 양 검색 경로 확인 |
| BI-001~003 | API enqueue/schema/worker entrypoint test | `bi-materialization` + `bi-question` ScaledJob E2E | 두 queue drain 및 PostgreSQL provenance 저장 |
| BEN-001~003 | API enqueue/schema/worker entrypoint test | benchmark queue + 두 workflow 비교 E2E | coordinator와 모든 비교 run이 Kubernetes, 중간/최종 결과 PostgreSQL 저장 |
| FE-001~005 | Vitest/MSW contract test | Playwright 제출·재연결 | 폐기 module/workflow ID 참조 0 |
| NFR-IO-001/002 | DB query projection/쓰기 단위 test | pg_stat_statements 측정 | summary에 vector 없음, progress full rewrite 없음 |
| NFR-ONCE-001 | 동시 claim/lease test | worker 강제 종료 후 복구 | 같은 lease generation 중복 실행 0 |
| NFR-SCALE-001 | 4개 ScaledJob manifest render test | KEDA 0→N→0 관찰 | workflow/BI 2종/benchmark backlog 기반 확장·축소 |
| 품질 게이트 | Ruff, Pyright, Pytest, Vitest, `npm build` | OpenAPI duplicate 검사 | warning으로 승인한 항목 외 전부 통과 |

## 필수 실행 순서

1. 순수 계약/단위 테스트
2. backend 전체 테스트와 정적 분석
3. frontend 테스트, typecheck, production build
4. Kubernetes manifest render와 schema 검증
5. PostgreSQL을 포함한 worker 통합 테스트
6. kind 또는 k3d에서 Excel/RAG/BI smoke E2E
7. API latency, summary payload 크기, DB query/write 빈도 측정

외부 LLM credential이 없는 CI에서는 provider를 deterministic fake로 대체하되 module/DAG/queue 경로는 실제 구현을 사용한다.

## 2026-08-23 로컬 Docker E2E 기준선

| 검증 대상 | 결과 | 관측값 |
| --- | --- | --- |
| Docker/k3d/KEDA | 통과 | Docker 29.5.3, `bist-local` 1/1, 표준 ScaledJob 4개 Ready |
| Excel ingestion | 통과 | `run-6a85410656404d6b8a427d85ad6cb749`, 1 sheet, 216 documents, `text-embedding-3-small` 7,374 tokens, 성공 노드 누적 16.47초, 전체 추적 비용 $0.00138348 |
| Hybrid RAG | 통과 | `run-c7be72014c2c4e3693f143c630db3b7e`, query embedding 1536D, keyword 2/dense 230/RRF 41건, FY2025 Revenue `120` 반환 |
| RAG 성능/비용 | 통과 | 성공 노드 누적 10.44초, Reader 2.77초, 추론 토큰 0, 추적된 총비용 $0.00159448, live run용 Kubernetes Job 1개 |
| Backend 품질 게이트 | 통과 | Pytest 92, Ruff, Pyright, Kubernetes 4개 manifest render, 잠금 Python 배포 진입점 검사 |
| Frontend 품질 게이트 | 통과 | Vitest 61, TypeScript typecheck, Vite production build |

성능 시간은 외부 큐 대기를 제외한 성공 노드 실행시간의 합이다. 비용은 Responses와 Embeddings usage를 현재 공식 단가로 계산한 값이며 PostgreSQL 연산 비용은 포함하지 않는다.
