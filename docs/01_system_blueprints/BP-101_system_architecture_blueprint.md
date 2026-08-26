# [BP-101] 시스템 전체 배치도 & 2-Tier 런타임 토폴로지
> **Document Code:** `BP-101` | **Category:** System Architecture Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`backend/bootstrap/container.py`](file:///c:/Repos/bist-mini-final/backend/bootstrap/container.py), [`backend/main.py`](file:///c:/Repos/bist-mini-final/backend/main.py), [`backend/core/settings.py`](file:///c:/Repos/bist-mini-final/backend/core/settings.py)

---

## 1. 시스템 아키텍처 토폴로지 (System Topology)

`bist-mini-final` 시스템은 비정형 스프레드시트 분석, 대규모 임베딩 색인, DAG 기반 RAG 실행, 그리고 실시간 재무 BI 대시보드를 통합 처리하기 위해 설계된 **엔터프라이즈 멀티 티어 하이브리드 아키텍처**를 가집니다.

```mermaid
flowchart TB
    subgraph ClientTier ["1. Client & Presentation Tier (React 18 + Vite)"]
        UI_PLAY["Playground WS (DAG Builder)"]
        UI_DS["Data Sources WS (VLM Viewer)"]
        UI_BI["Financial BI WS (Recharts Dashboard)"]
        UI_CHAT["[Planned] AI Financial Chatbot WS"]
        UI_COMP["[Planned] Company Comparison WS"]
    end

    subgraph GatewayTier ["2. Gateway & API Ingress Tier"]
        INGRESS["Kubernetes Ingress (Nginx / Traefik)"]
        CORS["CORS & RequestObservabilityMiddleware"]
        FASTAPI["FastAPI App ApplicationContainer"]
    end

    subgraph RuntimeTier ["3. 2-Tier Execution Runtime Tier"]
        direction TB
        subgraph Tier1 ["Tier 1: Synchronous In-Memory Engine (<100ms)"]
            T1_EXEC["WorkflowExecutor (Zero-I/O In-Memory Context)"]
            T1_REG["ModuleRegistry (19 Registered In-Memory Modules)"]
            T1_EXEC --- T1_REG
        end
        subgraph Tier2 ["Tier 2: Asynchronous Distributed Batch Engine"]
            K8S_DISP["KubernetesQueueDispatcher"]
            KEDA["KEDA ScaledJob / Celery Queue: workflow-core"]
            WORKER_POOL["Workflow Worker Pods (WorkerLease Locked)"]
            K8S_DISP --> KEDA --> WORKER_POOL
        end
    end

    subgraph ServiceDomain ["4. Domain Services Tier"]
        BI_SVC["BiApiServices (Document Profiler & Metric Engine)"]
        BM_SVC["BenchmarkService (Evaluation & Ground Truth)"]
        WF_SVC["WorkflowRuntimeServices (Run Store & History)"]
    end

    subgraph ProviderTier ["5. AI & Model Provider Tier"]
        OAI_LLM["OpenAIResponsesClient (GPT-4o / GPT-4o-mini)"]
        OAI_VLM["Luna VLM (GPT-4o Vision Image Parser)"]
        OAI_EMB["OpenAIEmbeddingEncoder (text-embedding-3-small 1536d)"]
        BGE_EMB["BgeEmbeddingEncoder (Local ONNX/PyTorch Fallback)"]
    end

    subgraph StorageTier ["6. Persistence & Storage Tier"]
        PG_POOL["Thread-Safe ConnectionPool (Min: 2, Max: 10)"]
        PG_CORE["PostgreSQL 16 Engine"]
        PG_VEC["pgvector (HNSW Index: m=16, ef_construction=64)"]
        PG_FTS["PostgreSQL Native FTS (TSVector & GIN Index)"]
        DISK_STORE["Artifact File System (/data/artifacts, /data/runs)"]
        PG_POOL --> PG_CORE
        PG_CORE --> PG_VEC
        PG_CORE --> PG_FTS
    end

    ClientTier --> INGRESS --> CORS --> FASTAPI
    FASTAPI --> ServiceDomain
    ServiceDomain --> Tier1
    ServiceDomain --> Tier2
    Tier1 --> ProviderTier
    Tier2 --> ProviderTier
    Tier1 --> StorageTier
    Tier2 --> StorageTier
```

---

## 2. 2-Tier 런타임 분기 알고리즘 (2-Tier Execution Routing)

파이프라인 실행 요청은 지연시간 요건(Latency Requirement)과 작업 부하량(Workload Mass)에 따라 동기 인메모리 런타임과 비동기 KEDA 큐 분산 워커 런타임으로 분기됩니다.

```mermaid
sequenceDiagram
    autonumber
    actor User as Client (Frontend/API)
    participant API as /api/workflows/run
    participant Disp as KubernetesQueueDispatcher
    participant T1 as Tier 1 In-Memory Engine
    participant KEDA as Tier 2 KEDA Queue
    participant DB as PostgreSQL (Runs & Leases)

    User->>API: POST /api/workflows/run (DAG Definition + Inputs + async_execution flag)
    alt async_execution == False (인터랙티브 디버깅 / Playground 단일 스텝)
        API->>T1: WorkflowExecutor.run_pipeline_sync(dag, inputs)
        T1->>T1: 위상 정렬 및 In-Memory 메모리 버스 전달
        T1-->>API: PipelineRunResult (Latency < 100ms)
        API-->>User: 200 OK + Instant Result Payload
    else async_execution == True (대용량 엑셀 VLM, BI Materialization, 벤치마크)
        API->>Disp: KubernetesQueueDispatcher.dispatch(run_id, payload)
        Disp->>DB: INSERT INTO workflow_runs (status='QUEUED')
        Disp->>KEDA: Push Job Payload to KEDA / Redis Queue
        Disp-->>API: RunDispatchAck (run_id)
        API-->>User: 202 Accepted + { run_id: "...", stream_url: "/api/workflows/runs/{run_id}/stream" }
        User->>API: GET /api/workflows/runs/{run_id}/stream (SSE Connect)
        Note over KEDA,DB: Worker Pod 스케일아웃 -> Lease 획득 -> 실행 -> SSE 이벤트 발송
    end
```

---

## 3. 부트스트랩 DI 컨테이너 구성 (Bootstrap Container Wireframing)

애플리케이션은 [`ApplicationContainer`](file:///c:/Repos/bist-mini-final/backend/bootstrap/container.py#L106-L140) 단일 진입점을 통해 모든 하위 의존성을 조립합니다.

```mermaid
classDiagram
    class ApplicationContainer {
        +RuntimeContainer runtime
        +KubernetesQueueDispatcher workflow_dispatcher
        +BiApiServices bi_services
        +create(runtime) ApplicationContainer
        +recover_pending_runs() int
        +close() void
    }

    class RuntimeContainer {
        +OpenAIProvider openai_provider
        +OpenAIResponsesClient completion_client
        +EmbeddingEncoder embedding_encoder
        +WorkflowRuntimeServices services
        +RuntimePaths paths
        +PgVectorConnectionProbe pgvector_probe
        +create(paths, initialize_schema) RuntimeContainer
        +close() void
    }

    class WorkflowRuntimeServices {
        +ModuleRegistry module_registry
        +WorkflowStore workflow_store
        +RunStore run_store
        +WorkflowExecutor workflow_executor
        +PgVectorStore pgvector_store
        +DatabaseManager db_manager
        +EmbeddingArtifactStore embedding_artifact_store
    }

    ApplicationContainer *-- RuntimeContainer
    RuntimeContainer *-- WorkflowRuntimeServices
```

---

## 4. 리팩토링 타깃 및 기술 부채 (Refactoring Targets & Debts)

### As-Is 분석 및 기술 부채
1. **`ApplicationContainer`의 단일 거대 조립 결합도**:
   - `create_workflow_runtime_services()` 내부에서 19개 모듈, DB 매니저, 파일 시스템 경로를 일괄 바인딩하여 단위 테스트 시 개별 모듈 격리 모킹(Mocking)이 번거로움.
2. **동기/비동기 실행 분기의 컨트롤러 계층 혼재**:
   - `workflow_routes.py`와 `benchmark_routes.py`에서 `workflow_dispatcher`와 `workflow_executor`를 직접 참조하여 if/else 분기하고 있음.

### To-Be 권장 리팩토링 설계 (Refactoring Blueprint)
1. **`ExecutionPort` 인터페이스 추상화**:
   ```python
   class ExecutionPort(ABC):
       @abstractmethod
       async def execute(self, command: RunWorkflowCommand) -> WorkflowExecutionHandle: ...
   ```
   - `DirectInMemoryExecutionAdapter`와 `KubernetesQueueExecutionAdapter`로 구현 분리.
2. **모듈 팩토리(Module Factory) 레이어 도입**:
   - 19개 모듈을 카테고리별(`QueryModulesFactory`, `RetrievalModulesFactory`, `VisionModulesFactory`)로 팩토리화하여 동적 로딩 가능하도록 분리.
