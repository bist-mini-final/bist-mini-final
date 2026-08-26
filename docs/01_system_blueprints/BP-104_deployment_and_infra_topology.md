# [BP-104] K8s, KEDA ScaledJob & 인프라 토폴로지
> **Document Code:** `BP-104` | **Category:** Infrastructure & DevOps Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`deploy/kubernetes/local.sh`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/local.sh), [`deploy/kubernetes/manifests/`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/manifests/), [`deploy/docker/`](file:///c:/Repos/bist-mini-final/deploy/docker/), [`deploy/compose/docker-compose.yml`](file:///c:/Repos/bist-mini-final/deploy/compose/docker-compose.yml)

---

## 1. 인프라 배치 토폴로지 (Infrastructure Topology)

`bist-mini-final`은 로컬 개발(Local k3d Cluster)부터 클라우드 프로덕션 Kubernetes 환경까지 동일한 매니페스트로 오케스트레이션되도록 설계되어 있습니다.

```mermaid
graph TB
    subgraph K8sCluster ["Kubernetes Cluster (Namespace: bist-batch)"]
        INGRESS["Ingress Controller (Port 80/443)"]
        
        subgraph FrontendGroup ["Frontend Pods (Nginx)"]
            FE["bist-frontend (Replicas: 1~3)<br>React 18 SPA Dist (/playground, /chatbot, /bi)"]
        end

        subgraph BackendGroup ["Backend API & Admin Pods (FastAPI)"]
            BE["bist-backend (Replicas: 2)<br>• REST API Core (/api/*)<br>• OpenAPI & ReDoc (/docs, /redoc)<br>• K8s Job Dashboard (/admin/jobs)"]
        end

        subgraph StorageGroup ["Storage StatefulSet"]
            PG["bist-postgres (pgvector 0.7.0 / PG 16)<br>PVC: 10Gi Local Path Storage"]
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
    INGRESS -->|/admin/jobs -> K8s Job Monitor| BE
    BE -->|SQL & Vector I/O| PG
    WORKER_PODS -->|Lease & Processing| PG
    KEDA_OP -->|Polls Queue Count| PG
    KEDA_OP -->|Triggers| SCALED_JOB
```

---

## 2. KEDA ScaledJob 자동 확장 메커니즘 (KEDA ScaledJob Specs)

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

## 3. 원클릭 로컬 배포 파이프라인 (`local.sh` Sequence)

개발자는 [`deploy/kubernetes/local.sh`](file:///c:/Repos/bist-mini-final/deploy/kubernetes/local.sh) 스크립트를 통해 원클릭으로 로컬 k3d 클러스터 생성, 이미지 빌드, DB 마이그레이션, KEDA 배포를 일괄 수행할 수 있습니다.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant Script as local.sh
    participant K3D as k3d Cluster (bist-local)
    participant DOCKER as Docker Engine
    participant K8S as kubectl & KEDA

    Dev->>Script: ./deploy/kubernetes/local.sh all
    Script->>DOCKER: ensure_docker & ensure_k3d
    Script->>K3D: k3d cluster create bist-local --port 8080:80@loadbalancer
    Script->>DOCKER: docker build -f deploy/docker/Dockerfile.backend -t bist-backend:local .
    Script->>DOCKER: docker build -f deploy/docker/Dockerfile.frontend -t bist-frontend:local .
    Script->>DOCKER: docker build -f deploy/docker/Dockerfile.worker -t bist-workflow-worker:local .
    Script->>K3D: k3d image import bist-backend:local bist-frontend:local bist-workflow-worker:local
    Script->>K8S: helm install keda kedacore/keda --namespace keda
    Script->>K8S: kubectl apply -f deploy/kubernetes/manifests/
    Script-->>Dev: ✅ Deployment Complete! Access at http://localhost:8080
```

---

## 4. 백엔드 내장 K8s 배치 잡 & 워커 관제 대시보드 (`GET /admin/jobs`)

일반 사용자 화면(React SPA)과 인프라 관제 화면을 분리하기 위해, FastAPI 백엔드는 `/docs` (Swagger UI), `/redoc` (ReDoc)과 유사하게 **백엔드 프로세스 자체에서 K8s 잡 & 워커 실시간 관제 대시보드를 서빙**합니다.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as DevOps / System Admin
    participant Ingress as Kubernetes Ingress (Port 8080)
    participant FastAPI as FastAPI Admin Router (GET /admin/jobs)
    participant SSE as K8s Stream Hub (GET /api/admin/jobs/stream)
    participant K8s as Kubernetes API (batch/v1, core/v1 Watch)
    participant DB as PostgreSQL (workflow_runs & Leases)

    Admin->>Ingress: GET /admin/jobs (브라우저 접속)
    Ingress->>FastAPI: HTML 대시보드 요청
    FastAPI-->>Admin: 200 OK (내장 경량 관제 대시보드 HTML/JS 반환)

    Admin->>SSE: EventSource 연결 (/api/admin/jobs/stream)
    SSE->>K8s: watch.Watch(list_namespaced_pod, namespace="bist-batch")
    SSE->>DB: SELECT * FROM workflow_runs WHERE status IN ('QUEUED', 'RUNNING')

    K8s-->>SSE: Pod 스케일아웃 감지 (bist-worker-abc: RUNNING)
    SSE-->>Admin: event: pod_status\ndata: {"pod": "bist-worker-abc", "run_id": "run-101", "cpu": "35%", "lease_ttl": 28}

    Admin->>FastAPI: GET /api/admin/jobs/bist-worker-abc/logs (로그 클릭)
    FastAPI->>K8s: read_namespaced_pod_log(follow=True)
    FastAPI-->>Admin: 실시간 컨테이너 stdout 로그 스트리밍 (Terminal 뷰어)
```

### 대시보드 주요 기능 및 관제 항목
1. **KEDA 스케일아웃 상태 모니터링**: 현재 활성 워커 Pod 수 (0 ~ N개), KEDA 큐 트리거 쿼리 카운트 실시간 표시.
2. **분산 Lease 락 관제**: 각 워커가 점유 중인 작업 ID(`run_id`), 임차권 만료 잔여시간(`TTL`), 하트비트 정상 여부 표시.
3. **실시간 컨테이너 로그 뷰어**: 터미널 없이 웹 브라우저 안에서 워커 Pod의 표준 출력(stdout/stderr) 로그 실시간 스트리밍.
4. **고아 작업 강제 회복 및 취소**: 장시간 응답 없는 워커의 Lease 강제 회수(`POST /api/admin/jobs/{run_id}/cancel`).

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
