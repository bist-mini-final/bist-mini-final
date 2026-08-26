# [BP-103] 분산 락, 임차권(Lease) & 경합 회복 시퀀스
> **Document Code:** `BP-103` | **Category:** Concurrency & Distributed Systems Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`backend/engine/worker/lease.py`](file:///c:/Repos/bist-mini-final/backend/engine/worker/lease.py), [`backend/engine/worker/main.py`](file:///c:/Repos/bist-mini-final/backend/engine/worker/main.py), [`backend/storage/db_manager.py`](file:///c:/Repos/bist-mini-final/backend/storage/db_manager.py)

---

## 1. 분산 동시성 제어 개요 (Concurrency Architecture)

Kubernetes 환경에서 수십 개의 Worker Pod가 단일 PostgreSQL `workflow_runs` 작업 대기열을 병렬로 소비할 때 발생할 수 있는 **4대 치명적 동시성 문제(Thundering Herd, 중복 실행, 좀비 덮어쓰기, 고아 작업)**를 원천 차단하기 위해 **3중 동시성 안전 분산 락킹 프로토콜(Triple Safety Locking)**을 구현합니다.

```mermaid
flowchart TD
    subgraph L1 ["Level 1: DB 행 수준 비차단 락 (FOR UPDATE SKIP LOCKED)"]
        P1["🛑 방어: Thundering Herd 및 작업 인출 대기 블로킹 방지"]
        M1["💡 원리: 다른 워커가 선점한 행은 대기 없이 0.1ms 만에 건너뛰고 다음 작업 획득"]
    end

    subgraph L2 ["Level 2: 세션 분산 자문 락 (pg_try_advisory_lock)"]
        P2["🛑 방어: 트랜잭션 커밋 후 장기 실행 중(In-Flight) 경합 및 프로세스 크래시 데드락 방지"]
        M2["💡 원리: 워커 TCP 세션과 바인딩되어, 워커 Pod가 OOM으로 죽으면 DB가 0초 만에 락 자동 반환"]
    end

    subgraph L3 ["Level 3: 동적 세대 임차권 (Lease Token & Heartbeat)"]
        P3["🛑 방어: 좀비 워커의 늦은 덮어쓰기(Split-Brain) 및 고아(Stalled) 작업 방치 방지"]
        M3["💡 원리: UUID 세대 토큰 검증 + 5초 주기 하트비트로 30초 무응답 시 자동 회수"]
    end

    L1 --> L2 --> L3
```

---

### 1.1 3중 동시성 안전 계층별 해결 문제 및 방어 매트릭스 (Problem-Solution Matrix)

| 안전 계층 (Level) | 핵심 기술 및 프로토콜 | 🛑 해결하는 핵심 문제점 (Problem) | 💡 동작 원리 및 아키텍처 보장 (Guarantee) |
| :--- | :--- | :--- | :--- |
| **Level 1: 인출 경합 방지**<br>(Row-Level Non-Blocking) | `SELECT ... FOR UPDATE SKIP LOCKED` | • **Thundering Herd 병목**<br>• **워커 프로세스 전체 블로킹**<br>• **동일 작업 중복 인출(Double Claim)** | 여러 워커가 동시에 큐를 폴링해도, 다른 워커가 잠근 행을 대기하지 않고 **즉시 건너뛰어(Skip) 0.1ms 만에 다음 빈 작업을 획득**하므로 락 대기 시간 0초 달성 및 완전 수평 확장. |
| **Level 2: 실행 중 상호 배제**<br>(Session-Level Advisory Lock) | `pg_try_advisory_lock(hashtext(...))` | • **트랜잭션 종료 후 실행 중 경합**<br>• **Redis 분산락 만료/TTL 데드락**<br>• **워커 OOM 크래시 시 락 잔존** | Level 1의 행 락은 `COMMIT` 즉시 풀리지만, Advisory Lock은 **파이프라인 실행(10~60초) 내내 세션 수준에서 유지**됨. 워커 Pod가 OOM/SIGKILL로 죽으면 **PostgreSQL 서버가 즉시 락을 0초 만에 자동 해제**하여 데드락 완전 배제. |
| **Level 3: 스플릿 브레인 방어**<br>(Generation Token & Heartbeat) | `WorkflowRunLease` (UUID) & `LeaseHeartbeat` (5초 주기) | • **지연된 좀비 워커의 결과 덮어쓰기**<br>• **네트워크 파티션 Split-Brain**<br>• **무한 대기 고아(Orphaned) 작업** | 작업 인출 시 고유한 UUID 세대 토큰을 발급. 지연된 구형 워커가 뒤늦게 결과를 쓰려 해도 `WHERE run_id = :id AND lease_token = :token` 불일치로 **DB 단에서 덮어쓰기 원천 거부(Rows Affected=0)**. 30초 무응답 시 다른 워커가 안전하게 회수. |

---

## 2. 작업 임차(Claim) 및 실행 라이프사이클 시퀀스 (Claim & Lease Sequence)

```mermaid
sequenceDiagram
    autonumber
    participant W as Worker Process (Pod)
    participant HB as LeaseHeartbeat Thread
    participant DB as PostgreSQL DBManager (workflow_runs)

    Note over W,DB: 1. 후보 작업 비차단 락 획득 (Level 1)
    W->>DB: claim_workflow_run_candidate(queue_name, worker_id)
    DB->>DB: SELECT run_id FROM workflow_runs ... FOR UPDATE SKIP LOCKED
    DB-->>W: WorkflowRunLease(run_id="run-123", token="uuid-token-gen1")

    Note over W,DB: 2. PostgreSQL Advisory Lock 획득 (Level 2)
    W->>DB: pg_try_advisory_lock(hashtext('workflow_run:' || run_id))
    alt Advisory Lock 획득 실패 (다른 프로세스 소유 중)
        W->>W: 후보 제외 목록 추가 후 다음 후보 탐색
    else Advisory Lock 획득 성공
        Note over W,DB: 3. 임차권 확정 및 세대 토큰 기록 (Level 3)
        W->>DB: finalize_workflow_run_claim(run_id, token, worker_id)
        DB->>DB: UPDATE workflow_runs SET status='running', lease_token=token, heartbeat_at=NOW()
        
        Note over W,HB: 4. 백그라운드 하트비트 스레드 기동 (5초 주기)
        W->>HB: LeaseHeartbeat.start()
        loop 매 interval_seconds (5초)
            HB->>DB: renew_lease_heartbeat(run_id, token)
            DB->>DB: UPDATE workflow_runs SET heartbeat_at=NOW() WHERE run_id=... AND lease_token=token
        end

        Note over W: 5. 파이프라인 실제 실행
        W->>W: WorkflowExecutor.run(dag, inputs)

        Note over W,HB: 6. 정상 종료 및 락 해제
        W->>HB: LeaseHeartbeat.stop()
        W->>DB: mark_workflow_completed(run_id, token, outputs)
        W->>DB: pg_advisory_unlock(...)
    end
```

---

## 3. 고아 작업 자동 회복 및 스톨 감지 FSM (Stale Recovery State Machine)

워커 프로세스가 OOM(Out of Memory)이나 Node Eviction으로 즉시 종료되어 정상적인 에러 기록을 남기지 못한 경우, 다음 워커가 스톨된 작업을 감지하여 안전하게 복구합니다.

```mermaid
stateDiagram-v2
    [*] --> QUEUED : 작업 발행 (available_at = NOW())
    QUEUED --> RUNNING : Worker Claim 성공 (lease_token 부여)
    
    state RUNNING {
        [*] --> ACTIVE_HEARTBEAT
        ACTIVE_HEARTBEAT --> ACTIVE_HEARTBEAT : 5초마다 heartbeat_at 갱신
        ACTIVE_HEARTBEAT --> STALE_HEARTBEAT : 워커 크래시 발생 (180초 경과)
    }

    RUNNING --> COMPLETED : 파이프라인 정상 완료
    RUNNING --> FAILED : 파이프라인 실행 중 예외 발생
    
    STALE_HEARTBEAT --> RE_QUEUED : 신규 워커가 stale_after_seconds(180s) 초과 감지 후 재임차
    RE_QUEUED --> RUNNING : 신규 Worker가 새 lease_token으로 실행 재개
    
    COMPLETED --> [*]
    FAILED --> [*]
```

---

## 4. 핵심 데이터 구조 및 DDL 명세

### `WorkflowRunLease` 구조체
```python
@dataclass(frozen=True)
class WorkflowRunLease:
    run_id: str
    token: str  # 임차권 세대 식별자 (UUID v4)
```

### `workflow_runs` 락킹 관련 핵심 컬럼
| 컬럼명 | 타입 | 제약 조건 및 역할 |
| :--- | :--- | :--- |
| `run_id` | `VARCHAR(64)` | PK, 고유 실행 식별자 |
| `queue_name` | `VARCHAR(64)` | 인덱스 대상 (`workflow-core`, `excel-ingestion`, `bi-materialize`) |
| `worker_id` | `VARCHAR(128)` | 현재 소유 워커 Pod 식별자 (예: `worker-pod-7df89-a1b2`) |
| `lease_token` | `VARCHAR(64)` | 세대 토큰. 이전 세대 토큰의 무단 DB 업데이트 방지 (`WorkflowLeaseLost`) |
| `heartbeat_at` | `TIMESTAMPTZ` | 마지막 생존 신호 타임스탬프 (인덱스: `(queue_name, status, heartbeat_at)`) |
| `cancel_requested`| `BOOLEAN` | 강제 취소 플래그 (True일 경우 하트비트 스레드가 실행 즉각 중단) |

---

## 5. 리팩토링 타깃 및 주의사항 (Refactoring Targets)

1. **Advisory Lock Key 해시 충돌 방지**:
   - As-Is: `hashtext('workflow_run:' || run_id)`로 32비트/64비트 정수 변환. 극단적인 대규모 실행 시 해시 충돌 가능성.
   - To-Be: 64비트 BigInt 해시 함수 또는 네임스페이스 분리형 `pg_advisory_xact_lock(class_id, obj_id)` 사용 권장.
2. **PostgreSQL 커넥션 타임아웃 & 고아 세션**:
   - 하트비트 갱신 실패 시 즉각적인 프로세스 자결(Self-Termination) 회로를 추가하여 Split-Brain 현상 방지.
