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

- 백엔드는 얇은 `entrypoints`, 단일 `bootstrap`, 도메인별 `domain/application/infrastructure/presentation/workers` vertical slice와 `platform` adapter 경계를 사용한다. 읽기 전용 작업 관제는 `operations` bounded context가 소유하며 구조 계약 테스트가 최상위 패키지와 의존 방향을 고정한다.
- 1단계 process/platform 경계는 실제 코드로 전환됐다. ASGI·CLI·worker는 `backend/entrypoints`, 조립은 `backend/bootstrap/application.py`, `http.py`, `workers.py`가 소유하며 여섯 worker 사양은 `backend.entrypoints.worker` 하나로 진입한다.
- `backend/api`는 domain router 결합, middleware, 예외 매핑, versioning, OpenAPI/SPA와 system probe 같은 공통 HTTP edge 정책만 보유한다. workflow, data sources, BI, company comparison, chatbot, benchmark, operations 및 module endpoint는 각 domain presentation이 소유한다.
- workflow는 `domain/application/infrastructure/presentation/workers` vertical slice다. run/queue/lease/history SQL과 schema는 `workflow/infrastructure/postgres`가 소유하고, domain·application·presentation·worker의 역방향 의존 금지와 process entrypoint 경계는 구조 계약 테스트가 검증한다.
- data sources는 `domain/application/infrastructure/presentation/workers` vertical slice로 이전됐다. 파일 저장·스프레드시트 렌더링·임베딩 artifact·분산 shard 실행은 data sources infrastructure가, 파일/ingestion/shard orchestration과 셀 근거·원본 artifact 조회는 application이 소유한다. 이전 API·storage·platform 호환 경로는 제거됐다.
- BI는 `domain/application/infrastructure/presentation/workers` vertical slice로 이전됐다. 저장소/provider 오류는 application 계약에서 번역하고 worker는 bootstrap을 생성하지 않고 주입된 runner/store만 실행한다. 이전 `features/bi`와 API 호환 경로는 제거됐다.
- company comparison은 `domain/application/infrastructure/presentation` vertical slice로 이전됐다. BI application facade는 comparison infrastructure adapter 뒤에 있고, 공통 snapshot protocol/PostgreSQL 구현은 각각 `shared/application`, `platform/postgres`가 소유한다. 이전 root/API 호환 경로는 제거됐다.
- chatbot은 `domain/application/infrastructure/presentation` vertical slice로 이전됐다. bootstrap이 `ChatApiServices`를 조립하고 presentation은 application facade만 받으며, 대화 정책·grounding·attachment·세션 저장의 이전 feature/API 경로는 제거됐다.
- benchmark는 `domain/application/infrastructure/presentation/workers` vertical slice로 이전됐다. 요청·평가 모델, 실행·채점 유스케이스, benchmark-set filesystem source, PostgreSQL queue, HTTP DTO와 주입형 worker가 분리됐으며 이전 feature/API 경로는 제거됐다.
- operations는 `domain/application/infrastructure/presentation` vertical slice로 이전됐다. workload·lease projection 모델, read-only query service, Kubernetes in-cluster/kubectl adapter와 `/jobs` presentation이 분리됐으며 이전 feature/provider/API 경로는 제거됐다.
- PostgreSQL pool과 범용 repository primitive는 `backend/platform/postgres`, pgvector Binary COPY와 오류 계약은 `backend/platform/pgvector`, OpenAI transport·Responses·embedding·pricing은 `backend/platform/openai`, Redis broker와 telemetry 구현은 각각 `backend/platform/redis`, `backend/platform/telemetry`가 소유한다. state stream, embedding port, lease worker와 observability context는 `backend/shared/application` 계약으로 분리됐다. collection catalog/retrieval/publish SQL gateway는 `data_sources/infrastructure/pgvector`로 이동했고 module은 좁은 port만 받는다.
- `backend/bootstrap`만 concrete adapter를 조립한다. `backend/features`, `backend/providers`, `backend/contracts`, `backend/engine`의 Python source와 `bootstrap/container.py`는 제거됐고 구조 계약 테스트가 재도입을 막는다. `backend/core`에는 런타임 설정만 남아 있다.
- `backend/storage`는 제거됐다. source-file/sheet repository와 schema는 data sources, workflow run/queue/lease/history repository와 schema는 workflow, chatbot schema는 chatbot이 소유한다. Bootstrap은 domain schema fragment와 concrete adapter를 조립만 한다. `backend/main.py`는 ASGI 외부 실행 호환 entrypoint로만 남아 있다.
- OpenAI Responses 호출은 provider가 transport와 응답 파싱을, `BaseLLMModule`이 structured/text/agentic module lifecycle과 usage 집계를 소유한다.
- spreadsheet 구조 감지는 전처리된 시트 계약, 병렬 분석 batch, 범위 정규화 단계를 분리하며 renderer는 값 포맷·fill·border·text 배치를 독립 helper로 유지한다.
- one-shot queue worker는 `LeasedWorker` template method를 상속해 claim, heartbeat, terminal transition을 공유한다. pause/cancel 같은 별도 상태 기계를 가진 worker는 공통 lease primitive만 재사용한다.
- HTTP와 worker는 request/run/job/worker correlation context를 공유한다.

## 검증 기준선

2026-08-31 로컬 전체 검증 결과:

- Backend: 295 passed, 2 skipped
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
