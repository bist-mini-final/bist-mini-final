# [BP-104] K8s, KEDA ScaledJob & 인프라 토폴로지
> **Document Code:** `BP-104` | **Category:** Infrastructure & DevOps Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`deploy/kubernetes/local.sh`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/local.sh), [`deploy/kubernetes/manifests/`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/manifests/), [`deploy/docker/`](file:///c:/Repos/bist-mini-final/deploy/docker/), [`deploy/compose/docker-compose.yml`](file:///c:/Repos/bist-mini-final/deploy/compose/docker-compose.yml)

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
            BE["bist-backend (Replicas: 2)<br>• REST API Core (/api/*)<br>• OpenAPI & ReDoc (/docs, /redoc)<br>• K8s Job Dashboard (/jobs)"]
        end

        subgraph OptionalStorageGroup ["Storage Layer (선택적 로컬 프로비저닝)"]
            PG_INTERNAL["[선택 옵션] 내장 bist-postgres (StatefulSet)<br>pgvector 0.7.0 / PG 16 (PVC: 10Gi)"]
        end

        subgraph KedaGroup ["Event-Driven Autoscaling (KEDA)"]
            KEDA_OP["KEDA Operator & Metrics Server"]
            SCALED_JOB["KEDA ScaledJob: workflow-core-scaledjob"]
            WORKER_PODS["Workflow Worker Pods (0 ~ N AutoScaled)"]
            SCALED_JOB -.->|Spawns| WORKER_PODS
        end
    end

    INGRESS -->|/ -> User Frontend UI| FE
    INGRESS -->|/api/* -> Core API| BE
    INGRESS -->|/docs, /redoc -> API Specs| BE
    INGRESS -->|/jobs -> K8s Job Monitor| BE
    
    BE -->|기본: 외부 DB 연결| PG_EXTERNAL
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
    START["🚀 배포 스크립트 실행<br>(./deploy/kubernetes/local.sh all 또는 local.ps1)"] --> PREFLIGHT{"1. Pre-Flight 환경 진단"}

    subgraph PreflightChecks ["5대 Pre-Flight 진단 항목"]
        C1["① OS & 쉘 환경 감지 (Win / Mac / Linux)"]
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
    TRACK_DECISION -- "K8s 비활성 / 경량 실행" --> TrackB

    TrackA --> READY["✅ 배포 완료! http://localhost:8080 즉시 접속"]
    TrackB --> READY
```

---

### 2.1 5대 Pre-Flight 사전 진단 및 자가 치료(Self-Bootstrapping) 원칙

| 진단 항목 | 발생 가능한 문제점 (Risk) | 자동 복구 및 자가 설치 동작 (Self-Healing) |
| :--- | :--- | :--- |
| **① OS & 쉘 호환성** | Windows 환경에서 bash `.sh` 미지원 | Windows 전용 **PowerShell 배포기(`deploy/kubernetes/local.ps1`)**와 POSIX bash(`local.sh`)를 듀얼 제공하여 크로스 플랫폼 지원. |
| **② 하드웨어 리소스** | 메모리 부족으로 K8s Pod OOM 크래시 | 가용 RAM을 사전 검사하여 4GB 미만일 경우 경고 알림 및 **경량 Track B(docker-compose) 전환 권고**. |
| **③ 포트 충돌 검사** | 기존 8080, 5432 포트 중복 점유 | 포트 충돌 감지 시 에러로 죽지 않고 환경 변수(`PORT=8081`)로 대체 포트 자동 바인딩 제안. |
| **④ Docker 엔진 검증** | Docker 미설치 또는 데몬 정지 | OS별 다중 Fallback(winget, curl 쉘, direct DMG/EXE 다운로드)을 통해 설치 가이드 및 데몬 기동 루프 실행. |
| **⑤ K8s CLI 도구 자동화** | `k3d`, `kubectl`, `helm` 미설치 | **패키지 매니저 유무와 무관하게**, 공식 정적 바이너리(Static Binary)를 프로젝트 로컬 디렉토리([`.tools/bin/`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/local.sh))에 자동 다운로드하여 `PATH`에 격리 바인딩. |

---

### 2.2 제로-디펜던시 환경별 다중 Fallback 설치 매트릭스 (All-Case Tool Installation Matrix)

새로운 순정 환경에는 패키지 매니저(`brew`, `winget`)나 기본 다운로더(`curl`, `wget`)조차 설치되어 있지 않을 수 있으므로, **다단계 폴백 체인(Fallback Chain)**을 통해 어떤 극한 환경에서도 100% 설치를 완수합니다:

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

1. **Track A (권장): Kubernetes + KEDA 분산 클러스터 (`deploy/kubernetes/local.sh all` 또는 `local.ps1 all`)**
   - 실제 운영 환경과 100% 동일하게 로컬 k3d 클러스터를 생성하고, KEDA 오토스케일러와 Ingress Controller를 통한 엔터프라이즈 멀티 티어 배포를 검증합니다.
2. **Track B (대체): Zero-K8s 경량 Docker-Compose (`docker compose -f deploy/compose/docker-compose.yml up -d`)**
   - K8s를 구동하기 어려운 저사양 노트북이나 CI 파이프라인에서 k3d 설치 없이 **동일한 프론트엔드/백엔드/PostgreSQL/워커 스택을 즉시 구동**하는 Fallback 트랙을 완벽히 보장합니다.

---

### 2.4 선택적 DB 프로비저닝 (External Managed DB 기본값 vs Internal StatefulSet 선택)

엔터프라이즈 프로덕션 환경과의 일치성을 위해 **외부 관리형 DB(External Managed PostgreSQL + pgvector) 연결이 기본값(Default)**으로 동작하며, 별도 DB가 없는 환경을 위해 **내장 DB 컨테이너 기동은 선택 옵션(Optional)**으로 제공됩니다:

| 구분 | [기본값] 외부 관리형 DB 연결 (Default Baseline) | [선택 옵션] 내장 DB 컨테이너 배포 (Optional Local DB) |
| :--- | :--- | :--- |
| **적용 시나리오** | **AWS RDS, Neon, Supabase, 호스트 자체 PostgreSQL 연결** | 로컬 머신에 별도 DB가 전혀 없는 개발/테스트 환경 |
| **실행 옵션** | `./deploy/kubernetes/local.sh all`<br>(기본값: 환경변수 `POSTGRES_HOST` / `.env` 참조) | `./deploy/kubernetes/local.sh all --with-embedded-postgres`<br>(내장 DB 자동 기동 플래그 명시 시) |
| **DB 컨테이너** | **내부 DB 컨테이너 생성 스킵** (5432 포트 충돌 및 메모리 낭비 0) | K8s `bist-postgres` StatefulSet 자동 기동 (PVC 10Gi) |
| **연결 바인딩** | 제공된 외부 DB 접속 정보(`Secret`/`ConfigMap`)를 백엔드/워커에 주입 | 클러스터 내부 서비스 DNS (`bist-postgres:5432`) 주입 |
| **KEDA 트리거** | 외부 DB `workflow_runs` 테이블을 원격 폴링하여 오토스케일링 | 내부 DB 큐 카운트 감지 |

---

## 3. KEDA ScaledJob 이벤트 기반 자동 확장 메커니즘 (KEDA ScaledJob Specs)

PostgreSQL 대기열 테이블 `workflow_runs`의 미처리 큐 개수에 따라 워커 Pod를 0개에서 최대 `KUBERNETES_MAX_JOBS`까지 동적으로 스케일아웃합니다.

### ScaledJob 매니페스트 발췌 (`deploy/kubernetes/manifests/scaledjob.yaml`)
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata:
  name: workflow-worker-scaler
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
  maxReplicaCount: 8
  triggers:
  - type: postgresql
    metadata:
      dbOwner: postgres
      host: bist-postgres
      port: "5432"
      userName: postgres
      passwordFromEnv: PG_PASSWORD
      query: "SELECT COUNT(*) FROM workflow_runs WHERE status = 'queued' AND available_at <= NOW();"
      targetQueryValue: "1"
```

---

## 4. 읽기 전용 K8s 배치 잡 & 워커 관제 (`/jobs`, `GET /api/v1/jobs`)

현재 승인 기준선은 React SPA의 `/jobs` 화면이 FastAPI의 `GET /api/v1/jobs`를 5초마다 조회하는 구조입니다. API는 KEDA `ScaledJob`, `batch/v1 Job`, `core/v1 Pod`의 요약 상태만 반환합니다. 클러스터 내부에서는 전용 ServiceAccount와 네임스페이스 한정 Role을 사용하고, 로컬 개발에서는 현재 `kubectl` context를 읽기 전용으로 조회합니다.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as DevOps / System Admin
    participant Ingress as Kubernetes Ingress (Port 8080)
    participant SPA as React Jobs Page
    participant FastAPI as FastAPI Job Router (GET /api/v1/jobs)
    participant K8s as Kubernetes API (keda.sh, batch/v1, core/v1)

    Admin->>Ingress: GET /jobs (브라우저 접속)
    Ingress->>SPA: 정적 SPA 및 /jobs route 반환
    SPA->>FastAPI: GET /api/v1/jobs (5초 polling)
    FastAPI->>K8s: list ScaledJobs, Jobs, Pods (bist-batch)
    K8s-->>FastAPI: resource status JSON
    FastAPI-->>SPA: KubernetesWorkloadSnapshot
    SPA-->>Admin: 상태 카드와 읽기 전용 표 갱신
```

### 대시보드 주요 기능 및 관제 항목
1. **구현됨 — KEDA/Job/Pod 상태 모니터링**: 이름, 상태, Ready, 성공/실패 수, 생성 시각, condition 메시지 표시.
2. **구현됨 — 최소 권한**: `pods`, `jobs`, `scaledjobs`의 `get/list/watch`만 허용하며 Secret, 로그, 생성·수정·삭제 권한은 부여하지 않음.
3. **To-Be — Lease/큐 상세 관제**: `workflow_runs`의 작업 ID, TTL, 하트비트와 Kubernetes 리소스의 상관관계 표시.
4. **To-Be — 로그 및 운영 명령**: 인증·감사·RBAC 정책이 확정되기 전까지 로그 스트리밍과 취소/회복 명령은 제공하지 않음.

---

## 5. 환경 변수 및 설정 배선 매트릭스 (Environment Matrix)

| 환경 변수명 | 기본값 | 용도 및 리소스 제약 |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | *(필수)* | GPT-5.6 Luna 추론 및 text-embedding-3-large (3072차원) 임베딩 호출 키 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API 게이트웨이 엔드포인트 |
| `PGVECTOR_URL` | `postgresql://postgres:postgres@localhost:5432/rag_flow` | PostgreSQL 16 + pgvector 데이터베이스 접속 DSN |
| `KUBERNETES_WORKFLOW_QUEUE`| `workflow-core` | KEDA 및 워커가 소비하는 기본 대기열 명칭 |
| `KUBERNETES_MAX_JOBS` | *(자동 감지)* | 최대 동시 스케일링 워커 Pod 수 |
| `KUBERNETES_JOB_CPU_REQUEST` | `1000m` | 워커 Pod CPU 요청량 (최소 1 코어) |
| `KUBERNETES_JOB_MEMORY_REQUEST`| `2Gi` | 워커 Pod RAM 요청량 (최소 2GB, VLM 렌더링 대비) |
| `DB_POOL_MIN_SIZE` / `MAX_SIZE`| `2` / `10` | FastAPI 프로세스당 커넥션 풀 크기 (워커는 1/4 크기 사용) |

---

## 6. 리팩토링 타깃 (Refactoring Targets)

1. **Helm Chart 표준화**:
   - As-Is: `deploy/kubernetes/manifests/` 디렉터리의 고정 yaml 파일들을 `kubectl apply`로 배포.
   - To-Be: Helm v3 Chart(`values.yaml`, `templates/`)로 통합하여 dev/staging/prod 환경 파라미터 분리.
2. **KEDA Trigger 인증 Secret 분리**:
   - `TriggerAuthentication` 리소스를 사용하여 DB 접속 비밀번호를 암호화된 K8s Secret으로 안전하게 바인딩.
