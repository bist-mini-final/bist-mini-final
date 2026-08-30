# [BP-104] K8s, KEDA ScaledJob & 인프라 토폴로지
> **Document Code:** `BP-104` | **Category:** Infrastructure & DevOps Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`deploy/kubernetes/local.sh`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/local.sh), [`deploy/kubernetes/manifests/`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/manifests/), [`deploy/helm/bist/`](file:///c:/Repos/bist-mini-final/deploy/helm/bist/), [`deploy/docker/`](file:///c:/Repos/bist-mini-final/deploy/docker/), [`deploy/compose/docker-compose.yml`](file:///c:/Repos/bist-mini-final/deploy/compose/docker-compose.yml)

---

## 1. 인프라 배치 토폴로지 (Infrastructure Topology)

`bist-mini-final`은 로컬 개발(Local k3d Cluster / docker-compose)부터 클라우드 프로덕션 Kubernetes 환경까지 동일한 아키텍처 원칙으로 오케스트레이션되도록 설계되어 있습니다.

```mermaid
graph TB
    subgraph ExternalDBGroup ["외부 관리형 DB (기본 연결 기준선 - Default Baseline)"]
        PG_EXTERNAL["외부 PostgreSQL 16 + pgvector 3072d<br>(AWS RDS / Supabase / Neon / 호스트 PostgreSQL)"]
    end

    subgraph K8sCluster ["Kubernetes Cluster (Namespace: bist-batch)"]
        INGRESS["Ingress Controller (Port 80/443)"]
        
        subgraph FrontendGroup ["Frontend Pods (Nginx)"]
            FE["bist-frontend (Replicas: 1~3)<br>React 18 SPA Dist (/playground, /chatbot, /bi)"]
        end

        subgraph BackendGroup ["Backend API & Admin Pods (FastAPI)"]
            BE["bist-backend (Replicas: 2)<br>• REST API Core (/api/v1/*)<br>• OpenAPI & ReDoc (/docs, /redoc)<br>• K8s Job Dashboard (/jobs)"]
        end

        REDIS["bist-redis<br>Pub/Sub state-change relay"]

        subgraph OptionalStorageGroup ["Storage Layer (선택적 로컬 프로비저닝)"]
            PG_INTERNAL["[선택 옵션] 내장 bist-postgres (StatefulSet)<br>pgvector 0.7.0 / PG 16 (PVC: 10Gi)"]
        end

        subgraph KedaGroup ["Event-Driven Autoscaling (KEDA)"]
            KEDA_OP["KEDA Operator & Metrics Server"]
            SCALED_JOB["6 ScaledJobs: workflow / ingestion embedding / ingestion vector / BI materialization / BI question / benchmark"]
            AUTH["TriggerAuthentication<br>bist-keda-postgresql Secret"]
            WORKER_PODS["One-shot Worker Pods (0 ~ N AutoScaled)"]
            SCALED_JOB -.->|Spawns| WORKER_PODS
            AUTH -.->|PostgreSQL connection| SCALED_JOB
        end
    end

    INGRESS -->|/ -> User Frontend UI| FE
    INGRESS -->|/api/* -> Core API| BE
    INGRESS -->|/docs, /redoc -> API Specs| BE
    INGRESS -->|/jobs -> K8s Job Monitor| BE
    
    BE -->|기본: 외부 DB 연결| PG_EXTERNAL
    BE -->|SSE state-change signal| REDIS
    BE -.->|선택: 내장 DB 활성화 시| PG_INTERNAL
    WORKER_PODS -->|기본: 외부 DB 연결| PG_EXTERNAL
    WORKER_PODS -.->|선택: 내장 DB 활성화 시| PG_INTERNAL
    KEDA_OP -->|기본: 외부 DB 큐 감지| PG_EXTERNAL
    KEDA_OP -.->|선택: 내장 DB 큐 감지| PG_INTERNAL
    KEDA_OP -->|Triggers| SCALED_JOB
```

---

## 2. 베이직 환경 적응형 로컬 배포 파이프라인 (Adaptive Zero-Config Deployment)

아무런 개발 도구(Docker, k3d, kubectl, helm 등)가 설치되어 있지 않은 **완전 순정(Fresh/Bare-Metal) OS 환경에서도 배포 실패 없이 구동**될 수 있도록, **5단계 사전 진단(Pre-Flight Diagnostics) ➡️ 제로-컨피그 자가 설치(Self-Bootstrapping) ➡️ 2-Track 배포 전략**을 구현합니다.

```mermaid
flowchart TD
    START["🚀 배포 스크립트 실행<br>(./deploy/kubernetes/local.sh all)"] --> PREFLIGHT{"1. Pre-Flight 환경 진단"}

    subgraph PreflightChecks ["5대 Pre-Flight 진단 항목"]
        C1["① Bash 실행 환경 감지 (WSL / Git Bash / macOS / Linux)"]
        C2["② 하드웨어 리소스 진단 (RAM >= 4GB, Disk >= 10GB)"]
        C3["③ 포트 충돌 검사 (Port 8080, 5432 점유 여부)"]
        C4["④ Docker 엔진 설치 및 데몬 기동 여부 검증"]
        C5["⑤ CLI 도구 존재 여부 (k3d, kubectl, helm, uv)"]
    end

    PREFLIGHT --> PreflightChecks
    PreflightChecks --> AUTO_INSTALL["2. 제로-글로벌 도구 자동 설치<br>(호스트 오염 없이 .tools/bin 로컬 격리 다운로드)"]

    AUTO_INSTALL --> TRACK_DECISION{"3. 배포 트랙 선택"}

    subgraph TrackA ["Track A: Full Kubernetes 모드 (표준 KEDA 클러스터)"]
        A1["k3d 클러스터 생성 (bist-local)"] --> A2["로컬 컨테이너 이미지 빌드"]
        A2 --> A3["KEDA Operator Helm 설치"]
        A3 --> A4["Ingress & ScaledJob 매니페스트 적용"]
    end

    subgraph TrackB ["Track B: Zero-K8s 경량 모드 (저사양/K8s 미지원 환경 Fallback)"]
        B1["docker-compose.yml 1-Click 구동"]
        B2["Nginx + FastAPI + PostgreSQL + Worker 컨테이너 일체 기동"]
    end

    TRACK_DECISION -- "K8s 지원 환경 (기본값)" --> TrackA
    TRACK_DECISION -- "K8s 비활성 / DB만 필요" --> TrackB

    TrackA --> READY["✅ 배포 완료! http://localhost:8080 즉시 접속"]
    TrackB --> READY
```

---

### 2.1 5대 Pre-Flight 사전 진단 및 자가 치료(Self-Bootstrapping) 원칙

| 진단 항목 | 발생 가능한 문제점 (Risk) | 자동 복구 및 자가 설치 동작 (Self-Healing) |
| :--- | :--- | :--- |
| **① OS & 쉘 호환성** | Windows 환경에서 bash `.sh` 미지원 | 단일 POSIX bash 배포기(`deploy/kubernetes/local.sh`)를 사용합니다. Windows에서는 WSL2 또는 Git Bash에서 실행합니다. |
| **② 하드웨어 리소스** | 메모리 부족으로 K8s Pod OOM 크래시 | 가용 RAM을 사전 검사하여 4GB 미만일 경우 경고 알림 및 **경량 Track B(docker-compose) 전환 권고**. |
| **③ 포트 충돌 검사** | 기존 8080, 5432 포트 중복 점유 | 포트 충돌 감지 시 에러로 죽지 않고 환경 변수(`PORT=8081`)로 대체 포트 자동 바인딩 제안. |
| **④ Docker 엔진 검증** | Docker 미설치 또는 데몬 정지 | OS별 다중 Fallback(winget, curl 쉘, direct DMG/EXE 다운로드)을 통해 설치 가이드 및 데몬 기동 루프 실행. |
| **⑤ K8s CLI 도구 자동화** | `k3d`, `kubectl`, `helm` 미설치 | **패키지 매니저 유무와 무관하게**, 공식 정적 바이너리(Static Binary)를 프로젝트 로컬 디렉토리([`.tools/bin/`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/local.sh))에 자동 다운로드하여 `PATH`에 격리 바인딩. |

---

### 2.2 제로-디펜던시 환경별 다중 Fallback 설치 매트릭스 (All-Case Tool Installation Matrix)

새 환경에서 패키지 매니저(`brew`, `winget`)나 기본 다운로더(`curl`, `wget`)의 가용성이 다를 수 있으므로, `local.sh`는 감지 가능한 설치·실행 경로를 순서대로 시도하고 실패 원인을 명확히 출력합니다:

```mermaid
flowchart TD
    subgraph DownloaderFallback ["1. 다운로더 도구 폴백 체인 (Download Tool Fallback)"]
        D1{"curl 존재하는가?"}
        D2{"wget 존재하는가?"}
        D3{"python3 (urllib) 존재하는가?"}
        D4["OS 네이티브 패키지 관리자로 curl 설치 (apt/dnf/apk/zypper)"]
        D_WIN["Windows: PowerShell 네이티브 Invoke-WebRequest 사용 (외부도구 0개 요구)"]

        D1 -- Yes --> EXEC_CURL["curl로 바이너리 다운로드"]
        D1 -- No --> D2
        D2 -- Yes --> EXEC_WGET["wget으로 바이너리 다운로드"]
        D2 -- No --> D3
        D3 -- Yes --> EXEC_PY["Python urllib으로 바이너리 다운로드"]
        D3 -- No --> D4
    end

    subgraph BinaryInstall ["2. 정적 바이너리 격리 배치 (Zero Global Pollution)"]
        B_K3D["k3d 바이너리 -> .tools/bin/k3d"]
        B_KUBECTL["kubectl 바이너리 -> .tools/bin/kubectl"]
        B_HELM["helm 바이너리 -> .tools/bin/helm"]
        B_UV["uv 바이너리 -> .tools/bin/uv"]
    end

    EXEC_CURL --> BinaryInstall
    EXEC_WGET --> BinaryInstall
    EXEC_PY --> BinaryInstall
    D_WIN --> BinaryInstall
```

| 대상 도구 | 1차 시도 (Primary) | 2차 폴백 (Fallback 1) | 3차 폴백 (Fallback 2 / Extreme) |
| :--- | :--- | :--- | :--- |
| **다운로더** | `curl` (기본 탑재 도구) | `wget` (대체 CLI) | `python3 -c "import urllib.request..."` 또는 Windows `Invoke-WebRequest` |
| **Docker Engine** | `winget` (Win) / `brew` (Mac) | `https://get.docker.com` (Linux 자동 쉘) | 공식 Docker Desktop Installer (.exe / .dmg) 직접 다운로드 후 실행 |
| **k3d** | OS 패키지 매니저 | 공식 인스톨 스크립트 (`install.sh`) | GitHub Releases Direct Static Binary (`.tools/bin/k3d`) |
| **kubectl** | OS 패키지 매니저 | `dl.k8s.io` 공식 정적 바이너리 직접 다운로드 | 프로젝트 로컬 격리 바인딩 (`.tools/bin/kubectl`) |
| **helm** | OS 패키지 매니저 | 공식 `get_helm.sh` 스크립트 | Tarball 아카이브 다운로드 후 `.tools/bin/helm` 압축 해제 |
| **권한 격리** | 일반 사용자 권한 (`non-root`) | `sudo` 없이 8080/8443 포트 사용 | 시스템 전역 디렉토리 침범 0건 (`.tools/bin/` 로컬 디렉토리만 사용) |

---

### 2.3 2-Track 배포 전략 (Enterprise K8s vs Zero-K8s Fallback)

1. **Track A (로컬 통합 검증): Kubernetes + KEDA (`deploy/kubernetes/local.sh all`)**
   - k3d, Redis, KEDA, NGINX Ingress, API/UI, 6개 워커 종류를 한 번에 배치합니다. 기존 클러스터에 8080/8443 포트가 없으면 스크립트가 삭제하지 않고 `recreate` 또는 `kubectl port-forward`를 안내합니다.
2. **Track B (DB 개발): Docker Compose (`docker compose -f deploy/compose/docker-compose.yml up -d`)**
   - Compose 파일은 PostgreSQL/pgvector 개발 DB만 관리합니다. API/UI는 README의 개발 서버 명령으로 별도 실행하고, one-shot 워커는 필요한 경우 수동 실행합니다.

---

### 2.4 데이터베이스 연결 안전성 (External DB vs Local Compose DB)

애플리케이션과 KEDA는 PostgreSQL/pgvector를 공통 상태 저장소와 큐로 사용합니다. `local.sh`의 연결 우선순위는 `KUBERNETES_DATABASE_URL` → `DATABASE_URL` → `PGVECTOR_URL`입니다.

| 구분 | 외부 관리형 PostgreSQL | 로컬 Compose PostgreSQL |
| :--- | :--- | :--- |
| **사용 시나리오** | 운영/스테이징 또는 원격 DB 검증 | k3d 및 개발 서버 로컬 검증 |
| **연결 전달** | `bist-batch-env`와 KEDA 전용 `bist-keda-postgresql` Secret | `KUBERNETES_DATABASE_URL=...localhost:5432/rag_flow` 일회성 재정의 |
| **사전 검증** | 인증 연결과 `SELECT 1` 성공 후에만 마이그레이션/배포 진행 | Compose DB healthcheck와 Alembic migration 확인 |
| **실패 처리** | 기존 로컬 DB 컨테이너와 클러스터를 건드리지 않고 중단 | 오류 원인을 출력하고 배포 중단 |

---

## 3. KEDA ScaledJob 이벤트 기반 자동 확장 메커니즘 (KEDA ScaledJob Specs)

PostgreSQL 대기열 테이블의 미처리 작업 수에 따라 워커 Pod를 0개에서 동적으로 스케일아웃합니다. 현재 `workflow-worker`, `ingestion-embedding`, `ingestion-vector`, `bi-materialization`, `bi-question`, `benchmark`의 여섯 ScaledJob을 사용하며, 각 트리거의 PostgreSQL 접속 문자열은 워커 환경 변수와 분리된 `TriggerAuthentication`에서 읽습니다. 전역 `KUBERNETES_MAX_JOBS`보다 phase별 안전 한도가 우선하며 embedding은 최대 4, vector COPY는 최대 2입니다.

### ScaledJob 매니페스트 발췌 (`deploy/kubernetes/manifests/scaledjob.yaml`)
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata:
  name: workflow-worker
  namespace: bist-batch
spec:
  jobTargetRef:
    template:
      spec:
        restartPolicy: Never
        containers:
        - name: worker
          image: bist-workflow-worker:local
          command: ["python", "-m", "backend.engine.worker.main"]
          resources:
            requests:
              cpu: 1000m
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 3Gi
  pollingInterval: 5
  successfulJobsHistoryLimit: 5
  failedJobsHistoryLimit: 10
  maxReplicaCount: 10
  triggers:
  - type: postgresql
    authenticationRef:
      name: bist-postgresql
    metadata:
      query: "SELECT COUNT(*) FROM workflow_runs WHERE status = 'queued' AND available_at <= NOW();"
      targetQueryValue: "1"
```

---

## 4. 읽기 전용 K8s 배치 잡 & 워커 관제 (`/jobs`, `GET /api/v1/jobs`)

현재 승인 기준선은 React SPA의 `/jobs` 화면이 FastAPI의 `GET /api/v1/jobs`를 5초마다 조회하는 구조입니다. API는 KEDA `ScaledJob`, `batch/v1 Job`, `core/v1 Pod` 요약과 PostgreSQL `workflow_runs`의 활성 큐/Lease 상태를 함께 반환합니다. 클러스터 내부에서는 전용 ServiceAccount와 네임스페이스 한정 Role을 사용하고, 로컬 개발에서는 현재 `kubectl` context를 읽기 전용으로 조회합니다.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as DevOps / System Admin
    participant Ingress as Kubernetes Ingress (Port 8080)
    participant SPA as React Jobs Page
    participant FastAPI as FastAPI Job Router (GET /api/v1/jobs)
    participant K8s as Kubernetes API (keda.sh, batch/v1, core/v1)
    participant DB as PostgreSQL workflow_runs

    Admin->>Ingress: GET /jobs (브라우저 접속)
    Ingress->>SPA: 정적 SPA 및 /jobs route 반환
    SPA->>FastAPI: GET /api/v1/jobs (5초 polling)
    FastAPI->>K8s: list ScaledJobs, Jobs, Pods (bist-batch)
    K8s-->>FastAPI: resource status JSON
    FastAPI->>DB: active queue/lease read-only query
    DB-->>FastAPI: run, worker, heartbeat age, TTL, attempts
    FastAPI-->>SPA: KubernetesWorkloadSnapshot
    SPA-->>Admin: 상태 카드와 읽기 전용 표 갱신
```

### 대시보드 주요 기능 및 관제 항목
1. **구현됨 — KEDA/Job/Pod 상태 모니터링**: 이름, 상태, Ready, 성공/실패 수, 생성 시각, condition 메시지 표시.
2. **구현됨 — 최소 권한**: `pods`, `jobs`, `scaledjobs`의 `get/list/watch`만 허용하며 Secret, 로그, 생성·수정·삭제 권한은 부여하지 않음.
3. **구현됨 — Lease/큐 상세 관제**: `workflow_runs`의 작업 ID, 큐, priority, 재시도 횟수, 하트비트 경과, 잔여 TTL, stale 여부와 Kubernetes Job/Pod 이름의 상관관계를 표시합니다. lease token 원문은 노출하지 않습니다.
4. **To-Be — 로그 및 운영 명령**: 인증·감사·RBAC 정책이 확정되기 전까지 로그 스트리밍과 취소/회복 명령은 제공하지 않음.

---

## 5. 환경 변수 및 설정 배선 매트릭스 (Environment Matrix)

| 환경 변수명 | 기본값 | 용도 및 리소스 제약 |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | *(필수)* | 설정된 OpenAI Responses 모델과 text-embedding-3-large (3072차원) 호출 키 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API 게이트웨이 엔드포인트 |
| `PGVECTOR_URL` | `postgresql://postgres:postgres@localhost:5432/rag_flow` | PostgreSQL 16 + pgvector 데이터베이스 접속 DSN |
| `REDIS_URL` | 없음 (k8s에서는 `redis://bist-redis:6379/0`) | API Pod 간 SSE 상태 변경 알림. 도메인 상태의 원본은 PostgreSQL이며 Redis 불능 시 폴링으로 대체 |
| `KUBERNETES_DATABASE_URL` | 없음 | `local.sh`에서 K8s용 DB를 별도 지정할 때의 최우선 DSN |
| `KUBERNETES_WORKFLOW_QUEUE`| `workflow-core` | KEDA 및 워커가 소비하는 기본 대기열 명칭 |
| `INGESTION_SHARDS_ENABLED` | `false` (K8s template은 `true`) | Excel embedding/COPY child Job fan-out 활성화 |
| `INGESTION_VECTOR_SHARD_SIZE` | `4096` | vector COPY Job 한 개의 문서 범위 |
| `KUBERNETES_MAX_JOBS` | *(자동 감지)* | 최대 동시 스케일링 워커 Pod 수 |
| `KUBERNETES_JOB_CPU_REQUEST` | `1000m` | 워커 Pod CPU 요청량 (최소 1 코어) |
| `KUBERNETES_JOB_MEMORY_REQUEST`| `2Gi` | 워커 Pod RAM 요청량 (최소 2GB, VLM 렌더링 대비) |
| `DB_POOL_MIN_SIZE` / `MAX_SIZE`| `2` / `10` | FastAPI 프로세스당 커넥션 풀 크기 (워커는 1/4 크기 사용) |

---

## 6. 구현 기준선과 남은 운영 과제

1. **구현됨 — Helm Chart 표준화**: `deploy/helm/bist/`가 API/UI/Redis, migration hook, RBAC, Ingress, 여섯 ScaledJob, `TriggerAuthentication`을 하나의 release로 렌더링합니다. `values.yaml`은 운영 기준, `values-k3d.yaml`은 로컬 검증 기준입니다.
2. **구현됨 — KEDA Trigger 인증 Secret 분리**: `bist-keda-postgresql` Secret의 `PGVECTOR_URL`을 `bist-postgresql` TriggerAuthentication이 참조합니다. DB URL은 ScaledJob metadata와 로그에 직접 넣지 않습니다.
3. **구현됨 — 다중 Pod SSE 알림**: `bist-redis`와 `REDIS_URL`이 Pub/Sub 변경 신호를 전달합니다. PostgreSQL 재조회와 0.5초 폴링 fallback으로 Pub/Sub 유실·장애가 상태 정합성을 손상시키지 않습니다.
4. **부분 구현 — 운영 관제 확장**: 읽기 전용 큐/Lease 상관관계는 구현됐습니다. 로그 스트리밍과 인증·감사가 수반되는 작업 제어는 별도 운영 정책이 확정될 때까지 제공하지 않습니다.
