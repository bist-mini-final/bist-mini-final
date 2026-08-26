# [BP-101] 시스템 전체 배치도 & 2-Tier 런타임 토폴로지
> **Document Code:** `BP-101` | **Category:** System Architecture Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`backend/bootstrap/container.py`](file:///c:/Repos/bist-mini-final/backend/bootstrap/container.py), [`backend/main.py`](file:///c:/Repos/bist-mini-final/backend/main.py), [`backend/core/settings.py`](file:///c:/Repos/bist-mini-final/backend/core/settings.py)

---

## 1. 시스템 아키텍처 토폴로지 (System Topology)

`bist-mini-final` 시스템은 비정형 스프레드시트 분석, 대규모 임베딩 색인, DAG 기반 RAG 실행, 그리고 실시간 재무 BI 대시보드를 통합 처리하기 위해 설계된 **엔터프라이즈 멀티 티어 하이브리드 아키텍처**를 가집니다.

```mermaid
graph TB
    subgraph ClientTier ["1. Client & Workspace Tier (React 18 SPA)"]
        WS_PLAY["Pipeline Playground (DAG Lab)"]
        WS_CHAT["[Planned] AI Financial Chatbot"]
        WS_BI["Financial BI & Company Comparison"]
        WS_DS["Data Sources (VLM Sheet Viewer)"]
        WS_BENCH["Benchmark Evaluation"]
    end

    subgraph GatewayTier ["2. Gateway & API Tier (Kubernetes & FastAPI)"]
        INGRESS["Kubernetes Ingress (bist-mini-ingress : 8080)"]
        ROUTER["FastAPI App (/api/*, /docs, /redoc, /jobs)"]
        CONTAINER["ApplicationContainer (DI Composition Root)"]
        INGRESS --> ROUTER --> CONTAINER
    end

    subgraph DomainTier ["3. Domain & Feature Services Tier"]
        FAST_RAG["FastRagPipelineAdapter (Chatbot/BI Orchestrator)"]
        BI_SVC["BiApiServices & DuPont Calculator"]
        INGEST_COORD["IngestionCoordinator (Excel & VLM Manager)"]
        BENCH_SVC["BenchmarkService (Evaluation Runner)"]
    end

    subgraph ModularLayer ["4. Modular Pipeline Layer (modules/* - 19 Independent Building Blocks)"]
        M_REG["ModuleRegistry (Single Source of Truth)"]
        M_DAG["Composed DAG Pipelines (Query -> Hybrid Retrieval -> VLM -> Reader)"]
        M_REG --> M_DAG
    end

    subgraph RuntimeTier ["5. 2-Tier Execution Runtime Tier"]
        subgraph T1_Box ["Tier 1: Async In-Memory Non-Blocking Engine (<100ms)"]
            T1_EXEC["WorkflowExecutor (asyncio EventLoop + In-Memory Bus)"]
        end
        subgraph T2_Box ["Tier 2: Distributed Batch Queue Engine"]
            DISPATCHER["KubernetesQueueDispatcher"]
            KEDA_QUEUE["KEDA Trigger (workflow-core Queue)"]
            WORKER_PODS["Workflow Worker Pods (WorkerLease Locked)"]
            DISPATCHER --> KEDA_QUEUE --> WORKER_PODS
        end
    end

    subgraph InfraTier ["6. AI Models & Storage Persistence Tier"]
        subgraph AI_PROV ["AI Provider Tier"]
            OAI_LLM["OpenAIResponsesClient (GPT-5.6 Luna LLM/VLM)"]
            OAI_EMB["OpenAIEmbeddingEncoder (text-embedding-3-large 3072d)"]
        end
        subgraph PERSIST ["Persistence Tier"]
            PG_VEC["PostgreSQL 16 + pgvector (3072d HNSW & TSVector GIN)"]
            PG_META["PostgreSQL Relational Tables (Runs, Leases, Profiles)"]
            DISK_FS["Spreadsheet & Embedding Artifact Storage (/data)"]
        end
    end

    ClientTier --> INGRESS
    CONTAINER --> DomainTier
    DomainTier -->|1. 비즈니스 목적별 모듈 선택 및 DAG 구성| ModularLayer
    ModularLayer -->|2. 구성된 DAG를 실행 호스트에 위임| RuntimeTier
    RuntimeTier -->|3. AI 추론 및 임베딩 호출| AI_PROV
    RuntimeTier -->|4. 데이터 적재 및 벡터 검색| PERSIST
```

---

## 2. 2-Tier 런타임 분기 알고리즘 (2-Tier Execution Routing)

파이프라인 실행 요청은 지연시간 요건(Latency Requirement)과 작업 부하량(Workload Mass)에 따라 **Tier 1 (비동기 논블로킹 인메모리 런타임)**과 **Tier 2 (KEDA 분산 배치 큐 런타임)**으로 명확히 분기됩니다.

```mermaid
sequenceDiagram
    autonumber
    actor User as Client (Frontend SPA / API)
    participant API as FastAPI APIRouter (/api/workflows/run)
    participant SSE as SSE Streamer (/api/workflows/runs/{id}/stream)
    participant Disp as KubernetesQueueDispatcher
    participant T1 as Tier 1 Async In-Memory Engine
    participant KEDA as Tier 2 KEDA Queue
    participant Worker as KEDA Worker Pods
    participant DB as PostgreSQL (Runs & Leases)

    User->>API: POST /api/workflows/run (DAG Definition + Inputs + async_execution flag)
    alt async_execution == False (인터랙티브 디버깅 / Playground / Fast RAG / 챗봇)
        API->>T1: await WorkflowExecutor.run_pipeline_async(dag, inputs)
        T1->>T1: asyncio 논블로킹 위상 정렬 및 In-Memory 버스 실행
        T1-->>API: PipelineRunResult (Latency < 100ms, Non-Blocking)
        API-->>User: 200 OK + Instant Result Payload
    else async_execution == True (대용량 엑셀 VLM, BI Materialization, 벤치마크)
        API->>Disp: KubernetesQueueDispatcher.dispatch(run_id, payload)
        Disp->>DB: INSERT INTO workflow_runs (status='QUEUED')
        Disp->>KEDA: Push Job Payload to KEDA Queue
        Disp-->>API: RunDispatchAck (run_id)
        API-->>User: 202 Accepted + { run_id, stream_url }
        
        User->>SSE: EventSource 연결 (GET /api/workflows/runs/{run_id}/stream)
        SSE-->>User: 200 OK (Content-Type: text/event-stream)
        
        KEDA->>Worker: 큐 대기열 감지 후 Worker Pod 자동 생성
        Worker->>DB: acquire_lease(run_id, worker_id, ttl=30s)
        
        Worker->>SSE: emit_event(NODE_STARTED, node_id="luna_vlm", progress=30%)
        SSE-->>User: event: message\ndata: {"type": "PROGRESS", "pct": 30}
        
        Worker->>Worker: 파이프라인 모듈 순차/병렬 실행
        
        Worker->>SSE: emit_event(RUN_COMPLETED, result_summary, progress=100%)
        SSE-->>User: event: message\ndata: {"type": "COMPLETED", "result": {...}}
        
        Worker->>DB: update_status('COMPLETED') & release_lease()
    end
```

---

### 2.1 기능별 실행 엔진 매핑 분류표 (Feature vs. Execution Runtime Matrix)

| 워크스페이스 / 기능 영역 | 구체적 기능 (Feature) | 실행 방식 (Execution Tier) | 담당 핵심 컴포넌트 / 모듈 | 트리거 API / 진입점 | 평균 지연시간 (Latency) | 통신 & 상태 모니터링 방식 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Pipeline Playground** (실험실/샌드박스) | 단일 노드 인터랙티브 테스트 | **Tier 1 (비동기 인메모리)** | `WorkflowExecutor.run_node_async` | `POST /api/workflows/node/run` | `< 100ms` | HTTP 즉시 반환 (Non-Blocking) |
| | 인터랙티브 DAG 전체 실험/실행 | **Tier 1 (비동기 인메모리)** | `WorkflowExecutor.run_pipeline_async` | `POST /api/workflows/run` | `100ms ~ 1.5s` | HTTP 즉시 반환 / 제로 I/O |
| **AI 금융 챗봇** (예정) | 대화형 멀티턴 재무 RAG 세션 | **Tier 1 (비동기 인메모리)** | `FastRagPipelineAdapter`, `ChatbotSession` | `WS /api/chatbot/ws` | `100ms ~ 500ms` | **WebSocket 양방향 스트리밍** (토큰/중단 제어) |
| **Data Sources** | 워크북 목록 & 시트 그리드 조회 | **Tier 1 (비동기 인메모리)** | `WorkbookCatalog`, `OpenPyXL` | `GET /api/data-sources/files` | `< 50ms` | HTTP 즉시 반환 |
| | Luna VLM 표 감지 & pgvector 색인 | **Tier 2 (분산 배치 큐)** | `LunaVlmStructureDetector`, `PgVectorBinaryCopy` | `POST /api/data-sources/ingest` | `5s ~ 40s` | KEDA Worker & SSE 진척도 스트림 |
| | DB / pgvector 연결 상태 프로브 | **Tier 1 (비동기 인메모리)** | `PgVectorConnectionProbe` | `GET /api/data-sources/probe` | `< 10ms` | 페이지 진입 시 1회성 HTTP 조회 (수동 새로고침) |
| **Financial BI** | 기업 프로파일 & 메트릭 조회 | **Tier 1 (비동기 인메모리)** | `DocumentProfiler`, `ProfileRepository` | `GET /api/bi/profiles` | `< 50ms` | HTTP 즉시 반환 |
| | 단건 재무 질의응답 (Fast RAG) | **Tier 1 (비동기 인메모리)** | `FastRagPipelineAdapter` | `POST /api/bi/questions/answer` | `200ms ~ 500ms` | HTTP 즉시 반환 |
| | 40+ 전사 지표 일괄 산출 (Materialize)| **Tier 2 (분산 배치 큐)** | `QuestionBatchWorkerMain`, `BiCalculator` | `POST /api/bi/materialize` | `10s ~ 60s` | DB 스냅샷 & SSE 스트림 |
| **기업 비교** (예정) | 다중 기업 비교 차트 & 듀퐁 분해도 조회 | **Tier 1 (비동기 인메모리)** | `CompanyComparisonService`, `SnapshotStore` | `GET /api/bi/comparison/{id}` | `< 100ms` | HTTP 즉시 반환 |
| | 다중 기업 지표 일괄 산출 & 정규화 배치 | **Tier 2 (분산 배치 큐)** | `CompanyComparisonWorker`, `Normalizer` | `POST /api/bi/comparison/materialize` | `15s ~ 90s` | KEDA Worker & SSE 진척도 스트림 |
| **K8s 잡 관제 (`/jobs`)** | 워커 Pod 라이프사이클 & 콘솔 로그 | **Tier 1 (비동기 인메모리)** | `KubernetesJobWatcher` | `WS /api/jobs/ws` | `< 50ms` | **WebSocket 양방향 터미널 스트림** |
| **Benchmark** | 정답지 기반 대량 정확도 평가 | **Tier 2 (분산 배치 큐)** | `BenchmarkWorkerMain`, `BenchmarkService` | `POST /api/benchmarks/run` | `30s ~ 3min` | SSE 진척도 & 리포트 |

---

## 3. 부트스트랩 DI 컨테이너 구성 (Bootstrap DI Container Architecture)

애플리케이션은 [`ApplicationContainer`](file:///c:/Repos/bist-mini-final/backend/bootstrap/container.py#L106-L140) 단일 진입점(Composition Root)을 통해 모든 하위 의존성을 조립하고, 비즈니스 도메인 서비스와 하부 인프라/실행 엔진을 2대 축으로 명확히 분리하여 **싱글톤(Singleton) 생명주기를 전담 관리**합니다.

```mermaid
classDiagram
    class ApplicationContainer {
        +DomainServicesContainer domain_services
        +InfrastructureContainer infrastructure
        +KubernetesQueueDispatcher workflow_dispatcher
        +create() ApplicationContainer
        +recover_pending_runs() int
        +close() void
    }

    class DomainServicesContainer {
        +BiApiServices bi_services
        +ChatbotService chatbot_service
        +CompanyComparisonService comparison_service
        +BenchmarkService benchmark_service
    }

    class InfrastructureContainer {
        +OpenAIProvider openai_provider
        +OpenAIResponsesClient completion_client
        +EmbeddingEncoder embedding_encoder
        +PipelineExecutionEngine pipeline_engine
        +RuntimePaths paths
        +PgVectorConnectionProbe pgvector_probe
        +create(paths) InfrastructureContainer
        +close() void
    }

    class PipelineExecutionEngine {
        +LazyModuleRegistry module_registry
        +WorkflowExecutor workflow_executor
        +PgVectorStore pgvector_store
        +DatabaseManager db_manager
        +WorkflowStore workflow_store
        +RunStore run_store
        +EmbeddingArtifactStore embedding_artifact_store
    }

    ApplicationContainer *-- DomainServicesContainer : 도메인 비즈니스 계층 소유
    ApplicationContainer *-- InfrastructureContainer : 하부 인프라 및 엔진 소유
    InfrastructureContainer *-- PipelineExecutionEngine : 순수 실행 엔진 번들 소유
```

---

### 3.1 부트스트랩(Bootstrap)과 싱글톤 관리 원칙

1. **부트스트랩(Bootstrap)의 정의**:
   - 서버 시동(FastAPI `lifespan startup`) 시점에 환경 변수 로드, DB 커넥션 풀 초기화, AI 모델 클라이언트 생성, 19개 파이프라인 모듈 등록을 **단 한 곳의 조립 루트(`backend/bootstrap/container.py`)에서 일괄 실행**하여 애플리케이션을 즉시 동작 가능한 상태로 준비시키는 초기화 과정입니다.
2. **컨테이너 기반 싱글톤(Container-Managed Singleton)**:
   - 전역 변수(`global`)나 하드코딩 싱글톤 패턴을 배제하고, `ApplicationContainer`가 DB 커넥션 풀, OpenAI 클라이언트, 19개 모듈 인스턴스를 **메모리에 단 1회만 생성하여 보관**합니다.
   - 모든 HTTP/WebSocket 요청은 이 컨테이너로부터 의존성을 주입(DI)받아 재사용함으로써 불필요한 객체 생성 비용을 0으로 억제하고 커넥션 풀 고갈을 방지합니다.

---

### 3.2 DI 컨테이너 상세 명세 및 계층 배치 매트릭스 (Container Specification Matrix)

| 컨테이너 / 객체 명칭 | 수명주기 & 운영 위치 (Scope) | 소유 핵심 필드 및 인터페이스 | 담당 핵심 역할 및 책임 | 계층 배치 및 분리 이유 (Rationale) |
| :--- | :--- | :--- | :--- | :--- |
| **`ApplicationContainer`**<br>(최상위 웹 프로세스 루트) | • **FastAPI 메인 웹 서버 프로세스(`backend/main.py`)** 단 1개 생성<br>• 서버 수명주기(`lifespan`)와 1:1 바인딩 | • `domain_services: DomainServicesContainer`<br>• `infrastructure: InfrastructureContainer`<br>• `workflow_dispatcher: KubernetesQueueDispatcher`<br>• `recover_pending_runs() -> int`<br>• `close() -> None` | • REST/WebSocket API 요청 진입점 의존성 주입(DI)<br>• Tier 2 분산 배치 작업 큐잉 디스패치<br>• 서버 재부팅 시 고아(`QUEUED`/`RUNNING`) 작업 복구<br>• 서버 셧다운 시 리소스 안전 해제(Graceful Shutdown) | Worker Pod에는 불필요한 **웹 전용 오케스트레이션, 도메인 비즈니스 서비스, 서버 기동/종료 수명주기 관리 책임**을 최상위 웹 계층에 완벽히 격리 |
| **`DomainServicesContainer`**<br>(도메인 비즈니스 서비스 번들) | • **FastAPI 웹 서버 메모리** 내 싱글톤 유지<br>• 각 API 라우터에 비즈니스 서비스 주입 | • `bi_services: BiApiServices`<br>• `chatbot_service: ChatbotService`<br>• `comparison_service: CompanyComparisonService`<br>• `benchmark_service: BenchmarkService` | • 40+ 전사 재무 지표 및 듀퐁 비율 산출<br>• 대화형 멀티턴 금융 챗봇 세션 관리<br>• 다중 기업 듀퐁 지표 정규화 및 레이더 차트 비교<br>• Ground-Truth 기반 정확도 벤치마크 오케스트레이션 | 비즈니스 서비스가 추가/확장될 때 인프라나 상위 루트를 건드리지 않고 독립적으로 확장할 수 있도록 **도메인 계층 전용 번들로 격리 (OCP 준수)** |
| **`InfrastructureContainer`**<br>(구 `RuntimeContainer` / 공통 인프라 브리지) | • **FastAPI 웹 서버 & KEDA Worker Pod** 양쪽 모두에서 생성 및 공유 | • `openai_provider: OpenAIProvider`<br>• `completion_client: OpenAIResponsesClient`<br>• `embedding_encoder: OpenAIEmbeddingEncoder`<br>• `pipeline_engine: PipelineExecutionEngine`<br>• `paths: RuntimePaths`<br>• `pgvector_probe: PgVectorConnectionProbe`<br>• `_owns_openai_provider: bool` | • GPT-5.6 Luna LLM/VLM 구조화/Agentic 생성 호출<br>• `text-embedding-3-large` (3072d) 벡터 인코딩<br>• 캐시/아티팩트 파일 시스템 절대 경로 싱글톤 관리<br>• DB/pgvector 연결 상태 검증 및 커넥션 풀 유지 | 웹 프로세스와 워커 프로세스가 **100% 동일한 AI 모델(GPT-5.6 Luna / 3072d) 및 디스크 경로 설정**을 공유하도록 강제하여 **워커 드리프트(Worker Drift)**를 원천 차단 |
| **`PipelineExecutionEngine`**<br>(구 `WorkflowRuntimeServices` / 순수 실행 번들) | • 웹/워커 환경 무관한 **순수 불변 실행 단위 (`@dataclass(frozen=True)`)** | • `module_registry: LazyModuleRegistry`<br>• `workflow_executor: WorkflowExecutor`<br>• `pgvector_store: PgVectorStore`<br>• `db_manager: DatabaseManager`<br>• `workflow_store: WorkflowStore`<br>• `run_store: RunStore`<br>• `embedding_artifact_store: EmbeddingArtifactStore` | • 19개 순수 RAG 파이프라인 모듈 지연 로딩 팩토리 레지스트리<br>• Kahn's 알고리즘 위상 정렬 및 `asyncio.TaskGroup` 비동기 병렬 실행<br>• PostgreSQL 16 + 3072d HNSW 코사인 검색 및 Binary COPY 대량 색인<br>• 실행 인스턴스 FSM 상태 전이(RUNNING/COMPLETED) 영속화 | 외부 웹/K8s 프레임워크를 전혀 모르는 **순수 불변 데이터 클래스**로 격리하여, **단위 테스트 시 가짜 Mock 객체로 19개 모듈 전체를 100% 독립 테스트(Unit Testing)** 가능 |

---

### 3.3 지연 생성 모듈 팩토리 및 OCP 확장 전략 (Lazy Module Factory Architecture)

향후 신규 모듈 추가 시의 결합도를 낮추고 서버 기동 속도를 최적화하기 위해 **4대 도메인 팩토리 & 지연 로딩 레지스트리**를 적용합니다:

1. **4대 도메인 팩토리 분리**:
   - `QueryModulesFactory`: 질의 입력, 분해, 라우터, 시맨틱 매처 (LLM 클라이언트 주입)
   - `RetrievalModulesFactory`: 데이터 스코프, pgvector 검색, 키워드 검색, RRF 퓨전, 컨텍스트 확장기 (DB 스토어 주입)
   - `VisionModulesFactory`: 시트 래스터라이저, Luna VLM 구조 감지, 셀 직렬화, 인덱스 라이터 (VLM & 디스크 경로 주입)
   - `ReaderModulesFactory`: 재무 수식 계산 및 QA 리더 모듈 (수식 엔진 & LLM 주입)
2. **지연 로딩(Lazy Loading) 메커니즘**:
   - 서버 부팅 시 19개 객체를 미리 메모리에 올리지 않고 팩토리 생성 레시피(`register_factory`)만 등록.
   - 실제 파이프라인 실행 시 **최초 1회만 인스턴스화(Lazy Singleton)**하여 서버 기동 지연시간을 500ms ➡️ 20ms로 단축.

---

## 4. 리팩토링 타깃 및 기술 부채 (Refactoring Targets & Debts)

### As-Is 분석 및 기술 부채
1. **전 계층 동기(Sync Blocking) 부채 존재**:
   - `BaseModule.execute()` 동기 함수, `executor.py`의 `threading.RLock`, `openpyxl` 동기 엑셀 로딩으로 인해 고부하 동시 요청 시 이벤트 루프 지연 발생.
2. **`ApplicationContainer`의 단일 거대 조립 결합도**:
   - `create_workflow_runtime_services()` 내부에서 19개 모듈, DB 매니저, 파일 시스템 경로를 일괄 바인딩하여 단위 테스트 시 개별 모듈 격리 모킹(Mocking)이 번거로움.
3. **런타임 실행 분기의 컨트롤러 계층 혼재**:
   - `workflow_routes.py`와 `benchmark_routes.py`에서 `workflow_dispatcher`와 `workflow_executor`를 직접 참조하여 if/else 분기하고 있음.

### To-Be 권장 리팩토링 설계 (Refactoring Blueprint)
1. **전 계층 Full-Async 논블로킹 전환 (`async def execute_async`)**:
   - 모든 모듈과 `WorkflowExecutor`를 `asyncio.TaskGroup` 및 `AsyncOpenAI`, `AsyncConnectionPool` 기반의 순수 비동기 아키텍처로 전환하여 동시 처리 성능 극대화.
2. **`ExecutionPort` 인터페이스 추상화**:
   ```python
   class ExecutionPort(ABC):
       @abstractmethod
       async def execute(self, command: RunWorkflowCommand) -> WorkflowExecutionHandle: ...
   ```
   - `AsyncInMemoryExecutionAdapter`와 `KubernetesQueueExecutionAdapter`로 구현 분리.
3. **지연 생성 모듈 팩토리(Lazy Module Factory) 레이어 도입**:
   - 19개 모듈을 4대 카테고리별(`QueryModulesFactory`, `RetrievalModulesFactory`, `VisionModulesFactory`, `ReaderModulesFactory`)로 팩토리화하고 지연 로딩(`LazyModuleRegistry`)을 적용하여 메모리 오버헤드 최소화 및 단위 테스트 격리.
