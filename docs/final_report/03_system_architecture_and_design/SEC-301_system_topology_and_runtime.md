# [SEC-301] 시스템 전체 토폴로지 및 Durable Job 런타임 조감도
> **Chapter:** 3. 시스템 아키텍처 및 상세 설계 | **Section:** 3.1 | **Status:** Implementation-aligned reference
> **Classification:** End-to-End System Topology & Durable Job Runtime Blueprint

---

## 1. 시스템 전체 배치도 (End-to-End System Topology)

`bist-mini-final`은 프론트엔드 React SPA, FastAPI 백엔드, PostgreSQL durable queue, Redis SSE 변경 신호, PostgreSQL 16 + pgvector 저장소, Kubernetes 분산 워커 클러스터로 구성됩니다.

```mermaid
flowchart TD
    subgraph ClientTier ["1. Client Tier (Vite + React 18 SPA)"]
        UI_PLAY["/playground (React Flow 2D DAG Sandbox)"]
        UI_DS["/data-sources (Spreadsheet Viewer & VLM Overlay)"]
        UI_BI["/dashboard (/bi alias, Financial BI)"]
        UI_CHAT["/chatbot (AI Financial Chatbot)"]
        UI_COMP["/company-comparison (Peer DuPont Comparison)"]
        UI_COMP_V2["/company-comparison-v2 (RAG Comparison)"]
    end

    subgraph ApiGatewayTier ["2. API Gateway & Presentation Tier (FastAPI)"]
        REST["REST API Endpoints (/api/v1/*)"]
        SSE["SSE Stream Hub (/api/v1/runs/{id}/stream and BI streams)"]
        AUTH["CORS, Global Exception Guard & DTO Validation"]
    end

    subgraph ExecutionTier ["3. Synchronous Read API & Durable Job Runtime"]
        subgraph ReadApi ["Synchronous read/calculation API"]
            BI_CALC["FinancialCalculator & BI Snapshot Query"]
        end
        subgraph DurableJobs ["Durable PostgreSQL Queue (KEDA Workers)"]
            DAG_EXEC["DAG Topology Executor (Kahn Topological Sort)"]
            LEASE["3-Level Concurrency Controller (SKIP LOCKED + Advisory Lock + Lease)"]
            KEDA_PODS["Kubernetes Worker Pods (ScaledJob Queue Workers)"]
        end
    end

    subgraph DataVisionEngine ["4. Data & Vision Processing Tier"]
        PARSER["OpenPyXL 2D Coordinate Normalizer"]
        LUNA_VLM["GPT-5.6 Luna VLM Vision Detector"]
        SERIALIZER["Cell Text Serializer (header_with_value)"]
        BINARY_COPY["PostgreSQL Native Binary COPY 3072d Ingestion Engine"]
    end

    subgraph PersistenceTier ["5. Persistence & Storage Tier"]
        PG_DB[("PostgreSQL 16 Database Engine")]
        PG_VEC["pgvector 3072d HNSW Index (Cosine)"]
        PG_FTS["TSVector BM25 Full-Text Search Index"]
        PG_TABLES["10 Relational Business Tables (workflow_runs, bi_snapshots, sheets...)"]
        REDIS["Redis Pub/Sub: optional SSE state-change hint"]
    end

    ClientTier <-->|HTTP REST / SSE| ApiGatewayTier
    ApiGatewayTier <-->|Direct Dispatch| ExecutionTier
    ExecutionTier <--> DataVisionEngine
    ExecutionTier <--> PersistenceTier
    DataVisionEngine -->|Binary COPY Stream| PersistenceTier
```

---

## 2. 현재 실행 경로 분리 아키텍처

| 실행 경로 | 구동 메커니즘 | 처리 작업 성격 | 상태 전달 |
| :--- | :--- | :--- | :--- |
| **동기 read/calculation** | FastAPI route → domain service → PostgreSQL | • BI 대시보드 스냅샷<br>• 기업 비교·리그<br>• 파일/인덱스 조회 | HTTP 응답 |
| **Durable job** | PostgreSQL queue + KEDA ScaledJob + lease | • 워크플로 DAG<br>• 인제스천·BI materialization/question·benchmark<br>• 채팅 RAG run | 상태 저장 후 SSE 또는 polling. Redis는 API Pod 간 SSE 갱신 신호만 전달 |
