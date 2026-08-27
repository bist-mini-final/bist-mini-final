# [SEC-303] 동적 시퀀스 다이어그램 & 분산 동시성 런북
> **Chapter:** 3. 시스템 아키텍처 및 상세 설계 | **Section:** 3.3 | **Status:** Approved Baseline  
> **Classification:** Dynamic Sequence Diagrams, 3-Level Distributed Locking & Ops Runbook

---

## 1. Fast RAG 인메모리 실시간 질의 시퀀스 (Fast RAG Sequence Trace)

[`FastRagPipelineAdapter`](file:///c:/Repos/bist-mini-final/backend/features/bi/fast_rag_adapter.py)는 무거운 DAG 인프라 오버헤드 없이 인메모리 포트 바인딩을 통해 단 300ms 이내에 하이브리드 검색 및 확장을 완료합니다:

```mermaid
sequenceDiagram
    autonumber
    actor User as Client UI (ChatbotView)
    participant WS as WebSocket Handler (WS /api/chatbot/ws)
    participant Adapter as FastRagPipelineAdapter
    participant Reg as ModuleRegistry
    participant PG as PostgreSQL (pgvector + FTS)
    participant LLM as GPT-5.6 Luna Financial Reader

    User->>WS: WebSocket Connect (Session Handshake)
    WS-->>User: 101 Switching Protocols (Session Ready)

    User->>WS: {"type": "USER_MESSAGE", "session_id": "s-1", "message": "SK하이닉스 2023년 영업적자 원인 및 규모는?"}
    WS->>Adapter: retrieve(BiRetrievalRequest)
    Adapter->>Reg: decomposer.execute(query)
    Adapter->>Reg: router.execute(subqueries)
    Adapter->>PG: parallel_dense_and_keyword_search()
    PG-->>Adapter: raw_candidates
    Adapter->>Reg: rrf_fusion.execute(dense, keyword)
    Adapter->>Reg: context_expander.execute(fused_hits)
    Adapter-->>WS: BiRetrievalResponse(expanded_context, cited_cells)

    WS->>LLM: stream_completion(expanded_context, prompt)
    loop Token Streaming
        LLM-->>WS: chunk_token ("영업손실은 약...")
        WS-->>User: {"type": "ANSWER_CHUNK", "text": "영업손실은 약..."}
    end
    WS-->>User: {"type": "ANSWER_DONE", "evidence": cited_cells}
```

---

## 2. 3-Level 동시성 안전 분산 락킹 시퀀스 (3-Level Distributed Locking)

Kubernetes 다중 워커 환경에서 작업 경합, 좀비 덮어쓰기 및 고아 작업을 방지하기 위한 3중 락 프로토콜입니다:

```mermaid
sequenceDiagram
    autonumber
    participant W as Worker Engine (Main Flow)
    participant HB as Background Heartbeat Task
    participant DB as PostgreSQL (workflow_runs)

    Note over W,DB: 1. Level 1: 후보 작업 비차단 락 획득 (SKIP LOCKED)
    W->>DB: claim_workflow_run_candidate(queue_name, worker_id)
    DB->>DB: SELECT run_id FROM workflow_runs ... FOR UPDATE SKIP LOCKED
    DB-->>W: WorkflowRunLease(run_id="run-123", token="uuid-gen1")

    Note over W,DB: 2. Level 2: PostgreSQL Advisory Lock 획득 (세션 분산 락)
    W->>DB: pg_try_advisory_lock(hashtext('workflow_run:' || run_id))
    DB-->>W: true (Lock Acquired)

    Note over W,DB: 3. Level 3: 5초 주기 Lease 하트비트 스레드 가동
    W->>HB: start_heartbeat(run_id, token, interval=5s)
    loop 매 5초마다 생존 갱신
        HB->>DB: UPDATE workflow_runs SET heartbeat_at=NOW() WHERE run_id=:id AND lease_token=:token
    end

    Note over W,DB: 4. 파이프라인 안전 완료 및 락 정상 해제
    W->>DB: mark_workflow_completed(run_id, token)
    W->>HB: stop()
    W->>DB: pg_advisory_unlock(hashtext('workflow_run:' || run_id))
```

---

## 3. 분산 인프라 운영 런북 및 장애 복구 절차 (Ops & Disaster Recovery Runbook)

| 장애 시나리오 (Scenario) | 감지 메커니즘 (Detection) | 자동 복구 절차 (Automated Recovery Sequence) | 운영자 수동 개입 지침 (Runbook Action) |
| :--- | :--- | :--- | :--- |
| **워커 Pod OOM / 노드 장애** | 5초 주기 하트비트 중단 ➡️ `heartbeat_at < NOW() - INTERVAL '30s'` | 1. PostgreSQL이 워커 세션의 `pg_advisory_lock`을 즉시 0초 해제.<br>2. 30초 경과 시 타 워커가 `STALLED` 상태 감지.<br>3. `reap_stalled_leases()`가 기존 토큰을 무효화하고 `status='queued'`로 전환. | k8s 워커 Pod의 메모리 리밋 증설 (`deploy/kubernetes/`) 및 `/jobs` 포털에서 큐 재유입 확인. |
| **PostgreSQL 일시적 연결 단절** | `psycopg2.OperationalError` 발생 | 1. 워커는 DB 업데이트 실패 시 `lease_token`을 상실한 것으로 간주하여 즉시 실행 중단.<br>2. 커넥션 풀이 지수 백오프(1s, 2s, 4s)로 재연결 시도. | DB 서버 리소스(CPU/메모리) 점유율 확인 및 `pg_stat_activity`에서 잔여 락 세션 점검. |
| **OpenAI Responses API 429 (Rate-Limit)** | ProviderApiError (HTTP 429) 반환 | 1. `BaseLLMModule`이 `Retry-After` 헤더를 파싱하여 최대 5회 지수 백오프 자동 재시도.<br>2. 재시도 초과 시 에러 엔벨로프 포장 후 큐에 재등록. | OpenAI 티어 할당량(TPM/RPM) 모니터링 및 KEDA 동시 워커 수 상한(`maxReplicaCount`) 조정. |
| **장기 실행 좀비 워커 발생** | 실행 시간이 `timeout_seconds` 초과 | 1. 워커 내부 비동기 타임아웃 트리거.<br>2. `cancel_requested=true` 플래그 감지 시 프로세스 안전 종료 및 롤백. | 필요 시 `/jobs` 관리자 콘솔에서 특정 `run_id`에 대해 강제 취소 명령(`POST /api/workflows/{id}/cancel`) 발행. |
