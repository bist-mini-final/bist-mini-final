# [BP-101] 시스템 전체 배치도 & 2-Tier 런타임 토폴로지
> **Document Code:** `BP-101` | **Category:** System Architecture Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`backend/bootstrap/container.py`](file:///c:/Repos/bist-mini-final/backend/bootstrap/container.py), [`backend/main.py`](file:///c:/Repos/bist-mini-final/backend/main.py), [`backend/core/settings.py`](file:///c:/Repos/bist-mini-final/backend/core/settings.py)

---

## 1. 시스템 아키텍처 토폴로지 (System Topology)

`bist-mini-final` 시스템은 비정형 스프레드시트 분석, 대규모 임베딩 색인, DAG 기반 RAG 실행, 그리고 실시간 재무 BI 대시보드를 통합 처리하기 위해 설계된 **엔터프라이즈 멀티 티어 하이브리드 아키텍처**를 가집니다.

```mermaid
flowchart TD
    classDef client fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0c4a6e;
    classDef gw fill:#f5f3ff,stroke:#7c3aed,stroke-width:2px,color:#4c1d95;
    classDef domain fill:#ecfdf5,stroke:#059669,stroke-width:2px,color:#064e3b;
    classDef t1 fill:#fffbeb,stroke:#d97706,stroke-width:2px,color:#78350f;
    classDef t2 fill:#fff1f2,stroke:#e11d48,stroke-width:2px,color:#881337;
    classDef dag fill:#fdf4ff,stroke:#c026d3,stroke-width:2px,color:#701a75;
    classDef infra fill:#f8fafc,stroke:#475569,stroke-width:2px,color:#0f172a;

    %% 1. 클라이언트 요청 계층
    subgraph L1_Client ["1. 클라이언트 워크스페이스 요청 계층 (Frontend SPA)"]
        UI_PLAY["Pipeline Playground<br>(실시간 단일 노드 / DAG 실험)"]:::client
        UI_CHAT["[Planned] AI Financial Chatbot<br>(대화형 재무 질의응답)"]:::client
        UI_BI["Financial BI & Company Comp<br>(단건 지표 조회 / 전사 산출)"]:::client
        UI_INGEST["Data Sources Management<br>(엑셀 업로드 & VLM 색인 요청)"]:::client
        UI_BENCH["Benchmark Evaluation<br>(정답지 기반 대량 평가 요청)"]:::client
    end

    %% 2. 게이트웨이 및 API 라우팅
    subgraph L2_Gateway ["2. 게이트웨이 & API 컨트롤러 계층 (FastAPI)"]
        INGRESS["Kubernetes Ingress (bist-mini-ingress : 포트 8080 단일 진입점)"]:::gw
        ROUTER["FastAPI APIRouter (/api/* 라우팅 및 DTO 스키마 검증)"]:::gw
        CONTAINER["ApplicationContainer (DI 조립 및 생명주기 관리)"]:::gw
        INGRESS --> ROUTER --> CONTAINER
    end

    %% 3. 도메인 서비스 및 오케스트레이터 계층
    subgraph L3_Domain ["3. 도메인 서비스 계층 (Business Logic & Flow Orchestration)"]
        FAST_RAG["FastRagPipelineAdapter<br>(챗봇/BI 전용 경량 RAG 오케스트레이터)"]:::domain
        BI_SVC["BiApiServices & Calculator<br>(40+ 재무 비율 산출 및 프로파일러)"]:::domain
        INGEST_SVC["IngestionCoordinator<br>(엑셀 VLM 분석 및 색인 작업 조율)"]:::domain
        BENCH_SVC["BenchmarkService<br>(정답 데이터셋 로드 및 배치 평가 조율)"]:::domain
    end

    %% 4. 2-Tier 실행 호스트 분기 계층
    subgraph L4_Hosts ["4. 2-Tier 파이프라인 조합 및 실행 호스트 (Execution Hosts)"]
        subgraph Tier1_Host ["Tier 1: 동기식 인메모리 제로 I/O 엔진 (<100ms)"]
            T1_EXEC["WorkflowExecutor<br>(FastAPI 프로세스 내 RAM 메모리 버스 고속 DAG 실행)"]:::t1
        end
        subgraph Tier2_Host ["Tier 2: 비동기식 분산 배치 큐 엔진 (KEDA ScaledJob)"]
            DISPATCHER["KubernetesQueueDispatcher<br>(workflow_runs 테이블 작업 큐잉)"]:::t2
            KEDA_QUEUE["KEDA Queue Trigger & Autoscaler<br>(대기열 감지 후 워커 Pod 동적 프로비저닝)"]:::t2
            WORKER_PODS["Standalone Worker Pods<br>(backend/engine/worker/main.py - Lease 분산락)"]:::t2
            DISPATCHER --> KEDA_QUEUE --> WORKER_PODS
        end
    end

    %% 5. 순수 파이프라인 모듈 코어 (동적으로 조립되는 DAG 파이프라인)
    subgraph L5_DAGs ["5. 파이프라인 모듈 코어 (modules/* - 동적 결선 및 실행)"]
        subgraph DAG_RAG ["(A) 하이브리드 RAG 질의응답 파이프라인"]
            M_DEC["Decomposer / Router<br>(원자적 분해 & 라우팅)"]:::dag
            M_RET["PgVector (Dense) ∥ TSVector (Sparse)<br>(3072d Cosine + BM25 병렬 검색)"]:::dag
            M_FUS["RrfFusion (k=60) & ContextExpander<br>(순위 융합 및 2D 그리드 셀 문맥 확장)"]:::dag
            M_READ["ReaderModule<br>(수식 검증 및 근거 기반 답변 생성)"]:::dag
            M_DEC --> M_RET --> M_FUS --> M_READ
        end

        subgraph DAG_INGEST ["(B) 엑셀 비전 구조 분석 및 대량 색인 파이프라인"]
            M_VLM["Sheet Image Rasterizer + Luna VLM<br>(GPT-5.6 Luna 표 바운딩박스 검출)"]:::dag
            M_SER["CellTextSerializer<br>(2D 그리드 셀 계층 직렬화)"]:::dag
            M_EMB["CellTextEmbedder<br>(3072차원 배치 임베딩 아티팩트 생성)"]:::dag
            M_COPY["PgVectorIndexWriter<br>(PostgreSQL Binary COPY 초고속 색인)"]:::dag
            M_VLM --> M_SER --> M_EMB --> M_COPY
        end
    end

    %% 6. 외부 AI 프로바이더 및 물리 영속성 계층
    subgraph L6_Infra ["6. AI 모델 프로바이더 & 물리 저장소 계층 (Infra & Storage)"]
        subgraph AI_PROV ["AI & Model Provider Ports"]
            OAI_LLM["OpenAIResponsesClient<br>(GPT-5.6 Luna 추론 및 비전 엔진)"]:::infra
            OAI_EMB["OpenAIEmbeddingEncoder<br>(text-embedding-3-large 3072d)"]:::infra
        end
        subgraph PERSIST ["PostgreSQL 16 + pgvector & Disk"]
            PG_VEC["langchain_pg_embedding<br>(3072d HNSW 벡터 + GIN TSVector)"]:::infra
            PG_META["PostgreSQL Tables<br>(runs, leases, profiles, snapshots)"]:::infra
            DISK_FS["Artifact Storage<br>(.xlsx 원본, 시트 PNG, 임베딩 .bin)"]:::infra
        end
    end

    %% === 실시간 호출 및 처리 흐름 배선 (Invocation Pathways) ===
    
    %% [경로 1: 빠른 인터랙티브 / 실시간 질의 경로 (Fast Path - Tier 1)]
    UI_PLAY -->|"(1-a) 동기 DAG 실험"| INGRESS
    UI_CHAT -->|"(1-b) 대화 질의"| INGRESS
    UI_BI -->|"(1-c) 단건 재무 질문"| INGRESS
    CONTAINER -->|"(2-a) 인메모리 위임"| FAST_RAG
    FAST_RAG -->|"(3-a) 즉시 실행 호출"| T1_EXEC
    T1_EXEC -->|"(4-a) RAG DAG 조립 및 구동"| DAG_RAG

    %% [경로 2: 중량 배치 / 대용량 비동기 큐 경로 (Batch Path - Tier 2)]
    UI_INGEST -->|"(1-d) 엑셀 색인 요청"| INGRESS
    UI_BENCH -->|"(1-e) 벤치마크 평가 요청"| INGRESS
    CONTAINER -->|"(2-b) 비동기 배치 위임"| INGEST_SVC
    CONTAINER -->|"(2-c) 대량 평가 위임"| BENCH_SVC
    INGEST_SVC -->|"(3-b) 작업 디스패치"| DISPATCHER
    BENCH_SVC -->|"(3-c) 작업 디스패치"| DISPATCHER
    WORKER_PODS -->|"(4-b) 색인 DAG 조립 및 구동"| DAG_INGEST
    WORKER_PODS -->|"(4-c) RAG DAG 대량 구동"| DAG_RAG

    %% [모듈과 AI/DB 인프라 간 I/O 연계]
    M_DEC & M_READ & M_VLM -->|LLM / VLM API 호출| OAI_LLM
    M_EMB & M_RET -->|3072d 임베딩 생성| OAI_EMB
    M_RET -->|HNSW 코사인 & BM25 검색| PG_VEC
    M_COPY -->|Binary COPY 초고속 적재| PG_VEC
    DISPATCHER & WORKER_PODS -->|상태 기록 & 분산 Lease 락| PG_META
    M_VLM & M_EMB -->|파일 읽기 & 아티팩트 I/O| DISK_FS
    
    %% [진척도 역방향 스트리밍]
    DISPATCHER -.->|"(5) SSE 스트림 실시간 중계"| ROUTER
    ROUTER -.->|SSE Events| UI_INGEST & UI_BENCH
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

### 2.1 기능별 실행 엔진 매핑 분류표 (Feature vs. Execution Runtime Matrix)

| 워크스페이스 / 기능 영역 | 구체적 기능 (Feature) | 실행 방식 (Execution Tier) | 담당 핵심 컴포넌트 / 모듈 | 트리거 API / 진입점 | 평균 지연시간 (Latency) | 상태 모니터링 방식 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Pipeline Playground** (실험실/샌드박스) | 단일 노드 인터랙티브 테스트 | **Tier 1 (동기 인메모리)** | `WorkflowExecutor.run_node_sync` | `POST /api/workflows/node/run` | `< 100ms` | HTTP 즉시 반환 |
| | 인터랙티브 DAG 전체 실험/실행 | **Tier 1 (동기 인메모리)** | `WorkflowExecutor.run_pipeline_sync` | `POST /api/workflows/run` | `100ms ~ 1.5s` | HTTP 즉시 반환 / 제로 I/O |
| **Data Sources** | 워크북 목록 & 시트 그리드 조회 | **Tier 1 (동기 인메모리)** | `WorkbookCatalog`, `OpenPyXL` | `GET /api/data-sources/files` | `< 50ms` | HTTP 즉시 반환 |
| | Luna VLM 표 감지 & pgvector 색인 | **Tier 2 (비동기 KEDA 큐)** | `LunaVlmStructureDetector`, `PgVectorBinaryCopy` | `POST /api/data-sources/ingest` | `5s ~ 40s` | KEDA Worker & SSE 진척도 |
| | DB / pgvector 연결 상태 프로브 | **Tier 1 (동기 인메모리)** | `PgVectorConnectionProbe` | `GET /api/data-sources/probe` | `< 10ms` | 3초 주기 HTTP 폴링 |
| **Financial BI** | 기업 프로파일 & 메트릭 조회 | **Tier 1 (동기 인메모리)** | `DocumentProfiler`, `ProfileRepository` | `GET /api/bi/profiles` | `< 50ms` | HTTP 즉시 반환 |
| | 단건 재무 질의응답 (Fast RAG) | **Tier 1 (동기 인메모리)** | `FastRagPipelineAdapter` | `POST /api/bi/questions/answer` | `200ms ~ 500ms` | HTTP 즉시 반환 |
| | 40+ 전사 지표 일괄 산출 (Materialize)| **Tier 2 (비동기 KEDA 큐)** | `QuestionBatchWorkerMain`, `BiCalculator` | `POST /api/bi/materialize` | `10s ~ 60s` | DB 스냅샷 & 큐 상태 |
| **AI 금융 챗봇** (예정) | 대화형 재무 RAG 질의응답 | **Tier 1 (동기 인메모리)** | `FastRagPipelineAdapter`, `ReaderModule` | `POST /api/chatbot/messages` | `300ms ~ 800ms` | SSE 토큰 스트리밍 |
| **기업 비교** (예정) | 다중 기업 듀퐁 분석 & 레이더 차트 | **Tier 1 (동기 인메모리)** | `QuestionSnapshotRepository`, `Normalizer` | `POST /api/bi/comparison` | `< 100ms` | HTTP 즉시 반환 |
| **Benchmark** | 정답지 기반 대량 정확도 평가 | **Tier 2 (비동기 KEDA 큐)** | `BenchmarkWorkerMain`, `BenchmarkService` | `POST /api/benchmarks/run` | `30s ~ 3min` | SSE 진척도 & 리포트 |

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
