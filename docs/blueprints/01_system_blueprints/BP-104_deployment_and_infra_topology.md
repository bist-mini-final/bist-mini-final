# [BP-104] K8s, KEDA ScaledJob & 인프라 토폴로지
> **Document Code:** `BP-104` | **Contract State:** Target Architecture | **Capability State:** Operational | **Structure State:** Complete
> **Target Ownership:** `deploy`, `backend/entrypoints/worker.py`, `backend/bootstrap/workers.py`, `backend/platform/kubernetes`, `backend/domains/operations`, `backend/domains/*/workers`, `jobs`
> **Current References:** [`deploy/kubernetes/local.sh`](../../../deploy/kubernetes/local.sh), [`deploy/kubernetes/manifests/`](../../../deploy/kubernetes/manifests), [`deploy/helm/bist/`](../../../deploy/helm/bist), [`deploy/docker/`](../../../deploy/docker), [`deploy/compose/docker-compose.yml`](../../../deploy/compose/docker-compose.yml)

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
            FE["bist-frontend (Replicas: 2 by default)<br>React 18 SPA (/chatbot, /playground, /data-sources, /dashboard, /company-comparison, /jobs, /settings)"]
        end

        subgraph BackendGroup ["Backend API & Admin Pods (FastAPI)"]
            BE["bist-backend (Replicas: 2)<br>• REST API Core (/api/v1/*)<br>• OpenAPI & ReDoc (/docs, /redoc)<br>• Job snapshot API (/api/v1/jobs)"]
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

## 2. 로컬 배포기와 실제 사전 조건

`deploy/kubernetes/local.sh`는 Docker 기반 로컬 통합 환경을 반복 가능하게 구성하는 Bash entrypoint입니다. 완전한 bare-metal 무의존 설치기는 아니며 Docker daemon과 Bash 실행 환경은 사전 조건입니다. Windows에서는 WSL2 또는 Git Bash에서 실행합니다.

```mermaid
flowchart TD
    START["./deploy/kubernetes/local.sh all"] --> CHECK["Docker daemon + k3d + kubectl + Helm + project Python 확인"]
    CHECK --> DB["로컬 Compose DB 시작 또는 외부 PostgreSQL SELECT 1 검증"]
    DB --> MIGRATE["alembic upgrade head"]
    MIGRATE --> CLUSTER["기존 bist-local 재사용 또는 k3d 생성"]
    CLUSTER --> CONTROL["KEDA + metrics-server + ingress-nginx 설치"]
    CONTROL --> IMAGE["backend/frontend/worker 이미지 build + k3d import"]
    IMAGE --> SECRET["application/KEDA Secret과 ScaledJob render"]
    SECRET --> APP["migration Job → API/UI/Redis rollout → readiness 확인"]
    APP --> READY["http://localhost:8080"]
```

### 2.1 도구 확인과 설치 범위

| 도구 | 현재 `local.sh` 동작 | 실패 시 경계 |
| :--- | :--- | :--- |
| Docker | 존재 여부와 daemon 응답 확인; macOS+Homebrew에서만 설치 시도 | 그 외 OS는 설치 안내 후 중단 |
| k3d | Homebrew 또는 공식 install script 사용 | downloader/권한 실패 시 중단 |
| kubectl | Homebrew 또는 `curl`로 공식 binary를 `.tools/bin`에 설치 | `curl`이 없거나 download 실패 시 중단 |
| Helm | Homebrew 또는 공식 `get_helm.sh` 사용 | 설치 후 실행 파일을 찾지 못하면 중단 |
| uv/Python | 프로젝트 `.venv`를 우선하고 필요 시 Homebrew 또는 uv installer로 `uv sync --frozen` | 프로젝트 dependency import 실패 시 중단 |
| Node/npm | 존재 여부 확인; macOS+Homebrew에서 설치 | 그 외 OS는 설치 필요 경고. container image build 자체는 Dockerfile에서 수행 |

RAM·disk·포트의 포괄적 preflight나 `wget`/PowerShell/urllib downloader chain은 현재 구현하지 않습니다. 동시 worker 상한은 배포 시 `capacity.py`가 Docker resource를 기준으로 계산하며, 기존 k3d cluster에 8080 ingress mapping이 없으면 자동 삭제하지 않고 `recreate` 또는 port-forward를 안내합니다.

### 2.2 지원 action과 파괴성 경계

| Action | 역할 | 상태 변경 범위 |
| :--- | :--- | :--- |
| `setup-tools`, `check` | 도구·프로젝트 Python 확인 | 필요한 도구 설치를 시도할 수 있음 |
| `cluster` | DB, k3d, KEDA, metrics-server, ingress 구성 | cluster/control plane 변경 |
| `build` | 3개 image build/import | container image와 k3d image store 변경 |
| `deploy` | DB migration, Secret, ScaledJob, API/UI/Redis 반영 | 기존 cluster를 보존하고 workload 갱신 |
| `all` | cluster + build + deploy + status | 표준 로컬 통합 배포 |
| `recreate` | 기존 지정 cluster 삭제 후 전부 재생성 | 명시적으로 `bist-local` cluster를 삭제 |
| `restart`, `down`, `destroy` | cluster 시작/중지/삭제 | action 이름에 표시된 cluster 상태만 변경 |
| `status`, `logs*` | resource/worker log 확인 | 읽기 전용 |

Compose는 PostgreSQL/pgvector 개발 DB만 관리하며 API/UI/worker 전체의 Kubernetes 대체 트랙이 아닙니다.

### 2.2.1 Host·공유기 포트 경계

- k3d load balancer는 host `8080 → Ingress 80`, host `8443 → Ingress 443`으로 생성됩니다. Windows Git Bash에서는 `cygpath -am`으로 data volume host 경로를 정규화하고 해당 k3d 호출에만 `MSYS_NO_PATHCONV=1`을 적용합니다. 재생성·삭제 전에는 PostgreSQL 컨테이너를 k3d 네트워크에서 분리하고 새 클러스터 생성 후 재연결하여 DB 데이터는 보존하면서 stale network를 방지합니다.
- 외부 DDNS 접속은 공유기 TCP `외부 8080 → Kubernetes host 고정 LAN IP:8080` 한 개로 구성합니다. Host IP는 DHCP 예약으로 고정합니다. React SPA와 `/api/*`가 같은 Ingress를 사용하므로 `5173`, `5183`, backend `8765`를 외부에 공개하지 않습니다.
- 외부 접속 전 관리자 권한으로 Windows Private profile의 TCP 8080 inbound rule을 등록하고 DDNS 공인 IP, 이중 NAT·CGNAT를 확인합니다. 외부 80을 내부 8080으로 전달하면 URL의 포트 표기를 생략할 수 있습니다.
- 검증 순서는 host `localhost:8080` → 같은 LAN의 `고정-IP:8080` → 모바일 데이터의 DDNS URL입니다. 같은 LAN의 DDNS 접속만 실패하면 공유기의 NAT loopback 미지원일 수 있으므로 외부망 결과로 판정합니다.
- 8443 매핑만으로 TLS가 활성화되지는 않습니다. 인증·인가가 없는 개발 배포는 VPN/source-IP 제한 뒤에서만 사용하며, 공개 서비스는 TLS reverse proxy와 인증 계층을 선행합니다.

---

### 2.3 Kubernetes 통합 배포와 DB 전용 개발 모드

1. **로컬 통합 검증: Kubernetes + KEDA (`deploy/kubernetes/local.sh all`)**
   - k3d, Redis, KEDA, NGINX Ingress, API/UI, 6개 워커 종류를 한 번에 배치합니다. 기존 클러스터에 8080/8443 포트가 없으면 스크립트가 삭제하지 않고 `recreate` 또는 `kubectl port-forward`를 안내합니다.
2. **DB 전용 개발: Docker Compose (`docker compose -f deploy/compose/docker-compose.yml up -d`)**
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

`bi-materialization`은 새 스냅샷마다 원본 워크북에서 기간·통화·배율 프로필을 다시 계산하고, `bi-question`은 저장 프로필 보완 경로를 수행할 수 있으므로 두 ScaledJob 모두 backend와 동일한 공유 데이터 볼륨을 `/app/data`에 마운트해야 합니다. 이 마운트가 빠지면 원본 워크북 조회가 실패해 LLM 프로필 fallback으로 내려가며 기간 축소나 `amount_unit_ambiguous`가 발생할 수 있으므로, 로컬 선언형 Job registry와 Helm `workerJobs[].mountData` 계약에서 모두 `true`로 고정합니다.

워커 release는 `bist.ai/image-revision`을 ScaledJob과 Pod template에 함께 기록하고 `rollout.strategy=immediate`를 사용합니다. 로컬 `:local` 태그는 Docker image ID를 revision으로 렌더링하고, Helm 운영 배포는 불변 image tag/digest를 전제로 image reference 해시를 기록합니다. 따라서 한 durable queue에 구형·신형 워커가 동시에 남아 서로 다른 BI catalog/formula 규칙으로 같은 스냅샷을 발행하지 않습니다. BI 질문 발행기는 저장된 `question_version`도 현재 catalog version과 대조하여 교차 버전 답변을 거부합니다.

DB DDL은 migration Job만 소유합니다. KEDA one-shot BI Pod는 `initialize_schema=False`로 기동하고 런타임 `CREATE/ALTER`를 수행하지 않습니다. 동시 scale-out 시 여러 워커가 PostgreSQL system catalog를 갱신해 시작 단계에서 deadlock을 일으키는 것을 방지하기 위한 배포 불변식입니다.

### 목표 worker entrypoint가 반영된 ScaledJob 규격
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
          command: ["python", "-m", "backend.entrypoints.worker"]
          args: ["workflow", "--queue", "workflow-core"]
          resources:
            requests:
              cpu: 1000m
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 3Gi
  pollingInterval: 2
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  maxReplicaCount: 4
  triggers:
  - type: postgresql
    authenticationRef:
      name: bist-postgresql
    metadata:
      query: >-
        SELECT COUNT(*) FROM workflow_runs
        WHERE queue_name = 'workflow-core'
          AND cancel_requested = FALSE
          AND ((status = 'queued' AND available_at <= NOW())
            OR (status = 'running' AND
                (heartbeat_at IS NULL OR heartbeat_at < NOW() - (180 * INTERVAL '1 second'))))
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
4. **범위 제외 — 로그 및 운영 명령**: 인증·감사·RBAC 정책이 확정되기 전까지 로그 스트리밍과 취소/회복 명령은 제공하지 않음. 이는 미완료 리팩토링이 아니라 보안 정책 경계임.

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
| `KUBERNETES_JOB_MEMORY_REQUEST`| `2Gi` | 워커 Pod RAM 요청량 (최소 2GB, spreadsheet 이미지 렌더링 대비) |
| `DB_POOL_MIN_SIZE` / `MAX_SIZE`| `2` / `10` | FastAPI 프로세스당 커넥션 풀 크기 (워커는 1/4 크기 사용) |

---

## 6. 구현 기준선과 운영 정책 경계

1. **구현됨 — Helm Chart 표준화**: `deploy/helm/bist/`가 API/UI/Redis, migration hook, RBAC, Ingress, 여섯 ScaledJob, `TriggerAuthentication`을 하나의 release로 렌더링합니다. `values.yaml`은 운영 기준, `values-k3d.yaml`은 로컬 검증 기준입니다.
2. **구현됨 — KEDA Trigger 인증 Secret 분리**: `bist-keda-postgresql` Secret의 `PGVECTOR_URL`을 `bist-postgresql` TriggerAuthentication이 참조합니다. DB URL은 ScaledJob metadata와 로그에 직접 넣지 않습니다.
3. **구현됨 — 다중 Pod SSE 알림**: `bist-redis`와 `REDIS_URL`이 Pub/Sub 변경 신호를 전달합니다. PostgreSQL 재조회와 0.5초 폴링 fallback으로 Pub/Sub 유실·장애가 상태 정합성을 손상시키지 않습니다.
4. **범위 결정 — 읽기 전용 운영 관제**: 큐/Lease 상관관계까지 제공하며 로그 스트리밍과 인증·감사가 수반되는 작업 제어는 별도 운영 제품·정책이 확정될 때까지 추가하지 않습니다.

---

## 7. 배포 소유권과 구조 완료 조건

- `deploy/`는 container image, Helm, raw manifest와 로컬 실행 UX를 소유하고 business queue 종류를 Python 분기로 재정의하지 않습니다.
- `jobs/`는 표준 Job 이름·command·resource profile을 선언하며 Helm/KEDA renderer가 같은 catalog를 소비합니다.
- `backend/platform/kubernetes`는 API client와 workload 조회·제출 adapter만 제공하고, 어떤 작업을 제출할지는 domain application port가 결정합니다.
- worker image의 정식 진입점은 `backend.entrypoints.worker` 하나이며 kind별 domain worker는 `backend.bootstrap.workers` registry에서 명시적으로 조립합니다.
- 모든 ScaledJob은 선언형 catalog와 통합 `backend.entrypoints.worker`를 사용하며 이전 `backend.engine` entrypoint는 제거됐습니다. renderer와 실제 manifest 계약이 계속 일치해야 합니다.
- raw manifest renderer와 Helm values는 같은 여섯 worker kind, queue, command, pending query와 phase별 replica 상한을 유지하며 CI가 선언형 `jobs` catalog와 렌더 결과를 대조합니다.
- image, queue, resource, Secret key, migration order 또는 local action을 바꾸면 Dockerfile/manifest/Helm/renderer/README와 BP-103·BP-503을 같은 변경에서 갱신합니다.
