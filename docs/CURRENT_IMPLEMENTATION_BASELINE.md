# 현재 구현 기준선

> **기준일:** 2026-08-31
> **제품 버전:** 0.1.0
> **공개 API:** `/api/v1`

이 문서는 As-Is 사실만 기록하는 현재 구현 기준선이다. 목표 구조, 허용 의존성과 완료 조건은 `docs/blueprints/README.md`와 개별 BP 문서를 따른다. 두 문서가 다를 때 현재 동작 확인에는 이 문서를, 변경 방향 판단에는 청사진을 사용한다.

## 제품 경계

- Pipeline Playground, Data Sources, Financial BI, AI Financial Chatbot, Company Comparison, Jobs, Settings를 제공한다.
- Financial BI와 Company Comparison은 독립 제품 도메인이다. 비교 도메인은 검증된 BI 스냅샷을 입력으로 읽지만 전용 API, DTO, 정책과 스냅샷 수명주기를 유지한다.
- 공개 REST namespace는 `/api/v1`이며 `/api`는 비노출 호환 alias다.

## 실행·저장 기준선

- PostgreSQL 16과 pgvector가 영속 상태의 단일 진실 공급원이다.
- Redis는 SSE 상태 변경 신호에만 사용한다.
- Kubernetes KEDA one-shot worker는 workflow, BI materialization, BI question, benchmark, ingestion embedding shard, ingestion vector shard의 6개 실행 사양을 가진다.
- Excel ingestion은 embedding 최대 4개, vector COPY 최대 2개 child shard로 fan-out한다.
- 벡터 적재는 float32 artifact와 PostgreSQL Binary COPY를 사용하며 발행 전 staging collection row count를 검증한다.

## RAG·분석 기준선

- `ModuleRegistry`의 실행 가능 모듈은 19개다.
- 검색은 Dense pgvector, PostgreSQL keyword, RRF와 2D context expansion을 사용한다.
- `Cell Value: ?`는 검색 표현에는 유지하지만 Reader 입력에서는 실제 값이 있는 근거만 허용한다.
- BI는 21개 근거 기반 지표를 제공하며 Company Comparison은 실제 BI 관측값만 사용한다.
- 표 구조 감지는 외부 OpenAI vision provider를 사용한다.

## 데이터베이스 기준선

- Alembic head는 `20260829_0005`다.
- 애플리케이션 테이블은 `alembic_version`을 제외하고 22개다.
- BI와 Company Comparison snapshot은 불변 발행본과 current pointer를 분리한다.
- workflow와 child shard queue는 lease token, heartbeat, stale recovery를 사용한다.

## 백엔드 구조 기준선

- 목표 구조는 얇은 `entrypoints`, 단일 `bootstrap`, 도메인별 `domain/application/infrastructure/presentation/workers` vertical slice와 `platform` adapter 경계를 사용한다. 읽기 전용 작업 관제는 `operations` bounded context가 소유한다. 현재 구현은 이 목표로 이동 중인 과도기 구조이며 완료 상태가 아니다.
- `backend/api`는 아직 도메인 route와 controller를 함께 보유한다. 최종적으로는 router 결합, middleware, exception handler, versioning만 남기고 도메인 presentation을 각 `backend/domains/<domain>/presentation`으로 이동한다.
- `backend/domains/<domain>/application`은 유스케이스와 port를, `domain`은 순수 상태·오류 규칙을 소유하는 것이 목표다. 현재 workflow와 BI는 비교적 분리돼 있지만 data sources, chatbot, benchmark, company comparison은 목표 하위 계층을 모두 갖추지 않았고 일부 application은 아직 `features`와 `engine` 구체 구현에 직접 의존한다.
- 현재 `backend/platform/pgvector`와 `backend/shared/infrastructure/database`가 좁은 저장소 adapter 경계를 제공한다. 최종 구조에서는 transaction protocol은 `shared/application`, driver·pool·transaction 구현은 `platform/postgres`, 도메인 SQL·mapping은 각 domain infrastructure로 이동한다. `DatabaseManager`와 `PgVectorStore`는 이 이동 중 호출을 보존하는 하위 호환 facade다.
- `backend/bootstrap`만 concrete adapter를 조립하는 것이 최종 규칙이다. 현재 `backend/features`, `backend/storage`, `backend/providers`, `backend/core`, `backend/contracts`, `backend/engine`은 호환성과 단계적 이전을 위해 남아 있으며 목표 디렉터리 구조의 최종 위치는 아니다.
- OpenAI Responses 호출은 provider가 transport와 응답 파싱을, `BaseLLMModule`이 structured/text/agentic module lifecycle과 usage 집계를 소유한다.
- spreadsheet 구조 감지는 전처리된 시트 계약, 병렬 분석 batch, 범위 정규화 단계를 분리하며 renderer는 값 포맷·fill·border·text 배치를 독립 helper로 유지한다.
- one-shot queue worker는 `LeasedWorker` template method를 상속해 claim, heartbeat, terminal transition을 공유한다. pause/cancel 같은 별도 상태 기계를 가진 worker는 공통 lease primitive만 재사용한다.
- HTTP와 worker는 request/run/job/worker correlation context를 공유한다.

## 검증 기준선

2026-08-31 로컬 전체 검증 결과:

- Backend: 235 passed, 2 skipped
- Frontend: 167 passed
- Ruff, Pyright, TypeScript typecheck, production build 통과
- Backend C901 migration budget: 0개(새 복잡도 hotspot 즉시 실패)
- Kubernetes renderer: 6개 `ScaledJob`

테스트 수는 구현 변경에 따라 달라질 수 있으며 성공 여부와 계약 검증을 기준으로 관리한다.

## 구조 변경 원칙

- Presentation → Application → Domain 의존 방향을 유지한다.
- Infrastructure는 Application에 정의된 port를 구현한다.
- Bootstrap만 구체 구현을 조립할 수 있다.
- 공통 상속은 동일한 lifecycle과 불변식을 가진 경우에만 사용하고, 도메인별 repository 계약은 명시적인 Protocol로 유지한다.
- 공개 API·DB schema·저장 데이터는 구조 리팩토링만으로 변경하지 않는다.
