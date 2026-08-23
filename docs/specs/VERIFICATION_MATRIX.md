# 검증 매트릭스

| 요구사항 | 자동 검증 | 통합/운영 검증 | 완료 조건 |
| --- | --- | --- | --- |
| MOD-001, JOB-001/002 | registry/job contract test, DAG compile test | 표준 workflow API 조회 | 모든 표준 Job이 포트 오류 없이 compile |
| RUN-001/002/008/009 | dispatcher 멱등성, API `202`, DB-required/progress failure test | PostgreSQL queue·node log·history backfill 확인 | API module execute 0회, DB 실패 시 메모리 fallback 0회 |
| RUN-003/004/005/010 | resume/cancel/SSE decoder·shared observer test | Pod 중단·lease recovery, Playground/ingestion 동시 관찰 | 성공 노드 중복 0, 동일 resource DB observer 1개, disconnect 후 완료 |
| ING-001~005 | fixture xlsx pipeline contract | kind/k3d + PostgreSQL E2E | source→index→metadata 모두 조회 가능 |
| RAG-001~005 | data-scope/router plan, model별 embedding, dense/keyword/RRF scope tests | seed DB 질의 E2E | 서브쿼리별 자동 collection 선택, 검색 범위 준수, 답변과 근거 확인 |
| BI-001~006 | API enqueue/schema/worker/SSE test | 실제 pgvector 기업 catalog + `bi-materialization`/`bi-question` ScaledJob E2E | DB 기업 노출, 0→N 병렬 처리, snapshot 재사용 및 provenance 저장 |
| BEN-001~003 | API enqueue/schema/worker entrypoint test | benchmark queue + 두 workflow 비교 E2E | coordinator와 모든 비교 run이 Kubernetes, 중간/최종 결과 PostgreSQL 저장 |
| FE-001~005/008 | Vitest SSE/API/hook contract test | 브라우저 기업 전환·실시간 진행·snapshot 렌더 | 제품 fixture import와 feature별 polling 0 |
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
| Hybrid RAG | 통과 | `run-10c66c08a55d411cb29b552a43e226ac`, catalog 8개에서 Router가 서브쿼리 1개를 동일 workbook의 concrete collection 2개에 매핑, keyword/dense/context가 그 ID만 사용, FY2025 Revenue `120 USD million`과 셀 근거 반환 |
| RAG 성능/비용 | 통과 | 성공 노드 누적 7.72초, Decomposer 2.14초, Router 2.24초, Reader 1.67초, 추적된 총비용 $0.00129346 |
| BI DB catalog/snapshot | 통과 | 실제 pgvector 기업 6개 노출, `job-4b57e58a09dfac76c962fabf`가 26개 질문을 `bi-question` 최대 7 Pod로 병렬 처리, SSE `13/26`→`14/26` 실시간 관찰, `snapshot-5e5ae931ce5c54537a3712b5` 원자 publish 후 KEDA active=false |
| BI snapshot 재사용 | 통과 | Bank of America published snapshot을 새 materialization 없이 API `200`, ETag 포함 약 122ms에 반환하고 브라우저 카드 렌더 확인 |
| Backend 품질 게이트 | 통과 | Pytest 100, Ruff, Pyright, Kubernetes 4개 manifest contract, 잠금 Python 배포 진입점 검사 |
| Frontend 품질 게이트 | 통과 | Vitest 76, TypeScript typecheck, Vite production build, 실제 브라우저 기업 전환·실패 복구 UI 확인 |
| Ingestion history DB backfill | 통과 | 기존 6개 collection에 완료 run 복구, 전체 8개 `by-index` API `200`, Luna table 1~56개 반환, 브라우저에서 기존 SPG workbook 구조 검사 modal 확인 |

성능 시간은 외부 큐 대기를 제외한 성공 노드 실행시간의 합이다. 비용은 Responses와 Embeddings usage를 현재 공식 단가로 계산한 값이며 PostgreSQL 연산 비용은 포함하지 않는다.

동일한 `workbook_hash`로 생성된 인덱스가 여러 개면 각각을 독립 collection으로 catalog에 노출한다. 현재 저장 모델에는 active/version 상태가 없으므로 catalog가 임의로 최신 하나를 숨기거나 삭제하지 않으며, Router가 선택한 ID 집합은 retrieval plan과 실행 결과에서 추적 가능하다.
