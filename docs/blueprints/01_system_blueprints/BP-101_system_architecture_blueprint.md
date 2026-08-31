# [BP-101] 시스템 전체 배치도와 실행 토폴로지
> **Document Code:** `BP-101` | **Contract State:** Target Architecture | **Capability State:** Operational | **Structure State:** Complete
> **Target Ownership:** `backend/entrypoints`, `backend/bootstrap`, `backend/domains`, `backend/platform`, `backend/shared`, `backend/api`, `modules`, `jobs`
> **Current References:** [`backend/entrypoints/`](../../../backend/entrypoints), [`backend/bootstrap/application.py`](../../../backend/bootstrap/application.py), [`backend/bootstrap/runtime.py`](../../../backend/bootstrap/runtime.py), [`backend/domains/`](../../../backend/domains), [`backend/platform/`](../../../backend/platform)

---

## 1. 목표 시스템 경계

이 시스템은 React SPA, FastAPI control plane, PostgreSQL/pgvector 영속 계층, Redis 상태 변경 신호, KEDA one-shot worker로 구성됩니다. 제품 워크스페이스는 Pipeline Playground, Data Sources, Financial BI, AI Financial Chatbot, Company Comparison, Jobs, Settings로 나뉩니다.

Financial BI와 Company Comparison은 별도 제품 도메인입니다. 비교 도메인은 BI 스냅샷을 검증된 원천으로 읽지만 전용 API, DTO, 점수 정책, 버전형 스냅샷 저장 수명주기를 소유합니다.

```mermaid
flowchart TB
    SPA["React SPA\nfeature workspaces"] --> API["FastAPI composition\n/api/v1"]
    API --> PRESENTATION["Domain presentation\nroutes + DTO + SSE"]
    PRESENTATION --> USECASE["Domain application\nports + use cases"]
    ENTRY["backend/entrypoints\nasgi + cli + worker"] --> BOOT["backend/bootstrap\napplication + http + workers"]
    BOOT --> PRESENTATION
    BOOT --> ADAPTERS["Domain infrastructure\nrepository + mapping"]
    BOOT --> PLATFORM["Platform adapters\nPostgreSQL + pgvector + OpenAI + K8s + Redis"]

    USECASE --> PGQ["PostgreSQL durable queues"]
    PGQ --> KEDA["KEDA ScaledJobs"]
    KEDA --> WORKERS["Domain one-shot workers\nlease + heartbeat"]
    WORKERS --> MODULES["ModuleRegistry\n19 registered module types"]

    PLATFORM --> OPENAI["OpenAI Responses + Embeddings"]
    PLATFORM --> PG["PostgreSQL 16 + pgvector"]
    PLATFORM --> REDIS["Redis Pub/Sub\nstate-change hints"]
    ADAPTERS --> PLATFORM
    ADAPTERS -.-> USECASE
```

표 구조 감지가 필요한 현재 경로는 외부 OpenAI vision provider를 사용하고, 검색 기준선은 Dense + PostgreSQL keyword + RRF + 2D context expansion입니다.
점선은 domain infrastructure가 application이 정의한 port를 구현한다는 뜻이며 application이 concrete adapter를 import한다는 뜻이 아닙니다.

---

## 2. 실행 모델

| 기능 | 요청 경계 | 실행/저장 방식 |
| :--- | :--- | :--- |
| 저장 워크플로 실행 | `POST /api/v1/workflows/{workflow_id}/runs` | PostgreSQL queue → KEDA worker → run/node 상태 영속화 |
| Data Sources 인제스천 | upload 또는 ingestion job API | durable workflow와 one-shot worker |
| BI materialization/question | `/api/v1/bi/*` | 전용 durable job과 SSE 진행 상태 |
| Chatbot | `/api/v1/chat/*` | 세션/메시지 영속화와 durable RAG run |
| Company Comparison 조회 | `GET /api/v1/company-comparisons/snapshot` | 현재 발행된 버전형 스냅샷 조회 |
| Company Comparison 갱신 | `POST /api/v1/company-comparisons/snapshot/refresh` | 짧은 결정론적 async 집계 후 원자적 head 전환 |
| Benchmark | `/api/v1/benchmarks/*` | durable benchmark job과 결과 행 영속화 |
| Jobs | `GET /api/v1/jobs` | Kubernetes workload와 queue/lease 읽기 전용 관제 |

Company Comparison refresh는 외부 LLM을 호출하지 않는 제한된 집계이므로 현재 요청 안에서 실행합니다. 처리량이 증가해 API 지연 예산을 넘을 때만 별도 durable materialization job으로 승격합니다.

---

## 3. 목표 부트스트랩 객체 그래프

```mermaid
classDiagram
    class ApplicationBootstrap {
        +build_shared_resources()
        +build_domain_adapters()
        +build_use_cases()
        +close()
    }
    class HttpBootstrap {
        +build_fastapi_app()
        +compose_domain_routers()
        +install_middleware()
    }
    class WorkerBootstrap {
        +build_worker(kind)
        +run_one_shot()
    }
    class DomainApplication {
        +commands
        +queries
        +ports
    }
    class DomainInfrastructure {
        +repositories
        +external_adapters
    }
    class PlatformAdapters {
        +postgres
        +pgvector
        +openai
        +kubernetes
        +redis
    }
    ApplicationBootstrap *-- DomainApplication
    ApplicationBootstrap *-- DomainInfrastructure
    ApplicationBootstrap *-- PlatformAdapters
    HttpBootstrap --> ApplicationBootstrap
    WorkerBootstrap --> ApplicationBootstrap
```

`application.py`의 `ApplicationContainer`는 공유 resource, domain adapter와 use case를 책임별 하위 container로 조립합니다. `http.py`는 FastAPI 수명주기와 domain router 결합만 담당하고, `workers.py`는 동일 object graph에서 one-shot worker를 선택해 실행합니다. 세 진입점은 설정과 adapter factory를 공유하지만 HTTP·worker 수명주기를 서로 끌어오지 않습니다. 이전 `bootstrap/container.py` 호환 경로는 제거됐고 현재 bootstrap package가 유일한 composition root입니다.

`backend/entrypoints`의 ASGI·CLI·worker 파일은 인자와 환경을 읽고 해당 bootstrap factory를 호출하는 얇은 process adapter입니다. 여기에는 repository 선택, route별 분기나 job policy를 두지 않습니다.

---

## 4. 상태와 장애 복구

1. PostgreSQL이 실행 상태의 단일 진실 공급원입니다.
2. Redis는 SSE가 저장 상태를 즉시 다시 읽도록 알리는 선택적 신호 계층이며 상태 원본이 아닙니다.
3. worker는 공통 `LeasedWorker` template의 lease token, heartbeat, terminal transition으로 중복 실행을 방지합니다. pause/cancel 상태 기계가 추가된 worker는 같은 `LeaseHeartbeat` primitive를 사용합니다.
4. API 재시작은 durable run을 취소하지 않으며 startup recovery가 미완료 queue 상태를 복구합니다.
5. BI와 comparison 스냅샷은 불변 발행본과 current pointer를 분리합니다. comparison의 current pointer는 복합 외래키로 같은 domain/scope만 참조할 수 있습니다.

---

## 5. 아키텍처 불변식

- 공개 API는 `/api/v1`을 기준으로 문서화합니다.
- domain은 application, infrastructure, presentation을 역참조하지 않습니다.
- application은 API, platform, provider, storage, engine concrete 구현을 역참조하지 않습니다.
- 서로 다른 domain은 상대 domain의 infrastructure를 import하지 않고 application port로 협력합니다.
- `modules/`는 DB/provider를 직접 생성하지 않고 주입받습니다.
- pipeline module은 `PgVectorStore` SQL gateway가 아니라 retrieval/ingestion/catalog port에 의존합니다.
- API 이벤트 루프에서 블로킹 DB·파일·CPU 작업을 직접 실행하지 않습니다.
- 비교 계산은 실제 BI 관측값과 원본 셀 근거만 사용하며 synthetic fallback을 만들지 않습니다.
- 현재 모듈 카탈로그는 `ModuleRegistry`에 등록된 19개 type이 단일 기준입니다.

정확한 현재 수치와 범위는 [`CURRENT_IMPLEMENTATION_BASELINE.md`](../../CURRENT_IMPLEMENTATION_BASELINE.md)를 우선합니다.

BP-102의 목표 트리와 import gate가 활성화됐고 수평 storage facade도 platform/domain infrastructure 경계로 분해됐습니다. 이후 구조 변경은 동일 gate를 통과해야 합니다.

---

## 6. 구현 정합성 판정

2026-08-31 기준 이 배치도는 현재 구현과 일치합니다.

- 추적되는 backend Python 최상위 패키지는 `api`, `bootstrap`, `core`, `domains`, `entrypoints`, `platform`, `shared`뿐이며 `core`에는 설정만 남아 있습니다.
- workflow, data sources, BI, company comparison, chatbot, benchmark, operations가 각각 vertical slice를 소유합니다.
- ASGI·worker·관리 명령은 `entrypoints → bootstrap` 방향으로만 시작하며 domain concrete adapter를 직접 조립하지 않습니다.
- OpenAPI 정식 namespace는 `/api/v1`, module registry는 19개 type, 제품 route는 새 채팅·플레이그라운드·데이터 소스·BI·기업 비교·작업 관제·설정으로 고정돼 있습니다.
- 구조 회귀는 `tests/modules/test_architecture_contracts.py`, 공개 API 회귀는 OpenAPI 계약 테스트, 런타임 수치는 `CURRENT_IMPLEMENTATION_BASELINE.md`에서 검증합니다.

새 bounded context, 외부 platform adapter, process entrypoint 또는 공개 workspace를 추가할 때 이 문서와 BP-102·BP-501·BP-601을 같은 변경에서 갱신해야 합니다.
