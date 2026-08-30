# [SEC-502] AST 아키텍처 불변식 정적 계약 테스트 결과
> **Chapter:** 5. 품질 검증 및 결론 | **Section:** 5.2 | **Status:** Approved Baseline  
> **Classification:** Static AST Architecture Invariants & Contract Verification Results

---

## 1. 3대 아키텍처 불변식 정적 검증 (`test_architecture_contracts.py`)

Python AST(Abstract Syntax Tree) 분석을 통해 소스코드의 의존성 방향을 정적으로 전수 검증합니다:

1. **규칙 1: Feature ➡️ API 역방향 참조 금지 (`features never imports backend.api`)** ➡️ **결과: 0건 (100% 통과)**
2. **규칙 2: Modules 내 인프라 직접 생성 금지 (`modules never constructs DatabaseManager, PgVectorStore...`)** ➡️ **결과: 0건 (100% 통과)**
3. **규칙 3: Kubernetes Worker Spec 불변식 검증 (`Jobs <-> K8s Manifest Sync`)** ➡️ **결과: 0건 (100% 통과)**

## 2. 비동기 경계 회귀 검증

- 전체 백엔드 테스트 결과: **175 passed, 2 skipped**.
- 프런트엔드 계약·컴포넌트 테스트 결과: **115 passed**이며 TypeScript 타입 검사와 프로덕션 빌드도 통과했습니다.
- Ruff lint와 Pyright 결과: **0 errors**.
- BI native async 조회·큐 등록, 기업 비교 스냅샷 발행·회귀 API, SSE async loader, 업로드 메타데이터 async 저장, async DAG의 동기 `RunStore` 스레드 격리를 계약 테스트로 검증했습니다.

## 3. 스키마와 실환경 smoke 검증

- Alembic head: `20260829_0005`.
- `ingestion_shards`의 prepare/claim/heartbeat/complete를 실제 PostgreSQL에서 확인하고, k3d `ingestion-vector` ScaledJob이 두 개의 COPY shard를 claim한 뒤 부모 barrier가 HNSW 생성과 atomic publish를 수행하는 smoke test를 통과했습니다. 테스트 collection·queue row·artifact는 검증 직후 제거했습니다.
- 로컬 PostgreSQL에 migration을 적용한 뒤 `GET /api/v1/company-comparisons/snapshot`과 `POST /api/v1/company-comparisons/snapshot/refresh`를 호출해 모두 200을 확인했습니다.
- 검증 데이터에서는 4개 기업과 108개 snapshot-local evidence가 반환됐습니다. 이 숫자는 API 계약의 고정값이 아니라 해당 로컬 데이터 상태의 smoke-test 결과입니다.
- 제거된 `/company-comparison-v2` frontend route와 legacy comparison API가 OpenAPI에 남지 않는지 계약 테스트로 확인합니다.
