# BIST Mini Final — RAG Pipeline & BI Visualizer

재무 스프레드시트 구조 분석, Luna VLM 테이블 감지, PostgreSQL/pgvector 하이브리드 검색(Dense + FTS + RRF), 근거 기반 응답, BI 대시보드 스냅샷 및 RAG 벤치마크를 제공하는 엔터프라이즈 RAG & BI 플랫폼입니다.

---

## 1. 시스템 아키텍처 및 큐 구조

```text
[Frontend: React/Vite/XYFlow]
        │ (HTTP / SSE)
        ▼
[Control Plane: FastAPI Backend (:8765)]
        │
        ├── PostgreSQL & pgvector (DB, Embeddings, Queue Tables)
        │     ├── bi_materialization_jobs / bi_questions / bi_answers
        │     ├── workflow_runs / workflow_leases
        │     └── benchmark_runs / benchmark_results
        │
        ▼ (KEDA Trigger & Autoscaling)
[Kubernetes Worker Pods / ScaledJobs]
        ├── workflow-core worker (RAG & Ingestion DAG 실행)
        ├── bi-materialization runner (지표 프로파일링 & 질문 생성)
        ├── bi-question batch worker (OpenAI Responses LLM 병렬 지표 추출)
        └── benchmark worker (파이프라인 평가 & 스코어링)
```

- **`modules/`**: 19개 파이프라인 모듈 및 Pydantic v2 계약의 단일 소스(Single Source of Truth).
- **`jobs/`**: 모듈 간 DAG 파이프라인 정의 및 배치 워커 엔트리포인트.
- **FastAPI Control Plane**: API 계약 검증, DB 큐 등록, 스냅샷/이슈 조회, SSE 실시간 스트리밍 제공.
- **KEDA ScaledJobs**: 4개 독립 큐(`workflow-core`, `bi-materialization`, `bi-question`, `benchmark`)에 쌓인 작업량에 따라 워커 Pod를 0부터 수평 자동 확장(HPA).

---

## 2. 원클릭 개발 환경 및 Kubernetes (k3d & KEDA) 배포 가이드

### 2.1 원클릭 일괄 설치 및 클러스터 구동 (`deploy/kubernetes/local.sh`)

`./deploy/kubernetes/local.sh all` 명령어 한 줄로 **필수 개발도구 자동 감지 및 설치부터 k3d 클러스터 구성, KEDA 오토스케일러, 워커 이미지 빌드/임포트, DB 스키마 동기화, KEDA ScaledJob 배포까지 모든 과정이 자동으로 완료**됩니다:

```bash
# 1. 전체 인프라 및 개발 도구 원클릭 일괄 설치 & 배포
./deploy/kubernetes/local.sh all

# 2. 클러스터 및 큐 상태 점검
./deploy/kubernetes/local.sh status
```

> **`local.sh` 자동화 범위:**
> - 미설치 도구 자동 감지 및 자동 설치 (`k3d`, `kubectl`, `helm`, `uv`, `node`)
> - Python 가상환경 및 잠금 의존성 자동 동기화 (`uv sync --frozen`)
> - Docker 데몬 자동 실행 확인
> - PostgreSQL DB 스키마 및 pgvector 확장 자동 검증
> - k3d 로컬 클러스터 (`bist-local`) 생성 및 KEDA v2.20.2 / Metrics Server 설치
> - 파이프라인 워커 이미지 빌드 및 클러스터 자동 임포트
> - 네임스페이스(`bist-batch`), 시크릿(`bist-batch-env`), 4종 ScaledJob 매니페스트 동적 렌더링 및 적용

#### 특정 단계별 개별 제어 명령어:
```bash
./deploy/kubernetes/local.sh setup-tools # 개발 도구 및 가상환경만 설치
./deploy/kubernetes/local.sh cluster     # k3d 클러스터 & KEDA 설치
./deploy/kubernetes/local.sh build       # 워커 이미지 빌드 및 k3d import
./deploy/kubernetes/local.sh deploy      # ScaledJob 및 Secret 적용
./deploy/kubernetes/local.sh status      # 클러스터, Pod, ScaledJob 상태 확인
./deploy/kubernetes/local.sh logs        # 워커 Pod 실시간 로그 출력
./deploy/kubernetes/local.sh down        # 로컬 클러스터 정지
./deploy/kubernetes/local.sh destroy     # 로컬 클러스터 완전 삭제
```

---

### 2.2 필수/권장 도구 목록 및 수동 설치 (참고용)

도구를 직접 수동으로 설치하고자 할 경우 아래 표와 명령어를 참고하세요.

| 도구 | 권장 버전 | 용도 | macOS (Homebrew) | Linux / 기타 |
| :--- | :--- | :--- | :--- | :--- |
| **Docker** | 24.0+ | 컨테이너 엔진 및 런타임 | Docker Desktop / OrbStack | Docker Engine |
| **k3d** | v5.6+ | Docker 위에서 구동되는 경량 k3s 클러스터 관리 | `brew install k3d` | `curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh \| bash` |
| **kubectl** | v1.28+ | Kubernetes 클러스터 CLI | `brew install kubectl` | `curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl` |
| **helm** | v3.12+ | KEDA 및 Metrics Server 설치용 패키지 매니저 | `brew install helm` | `curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \| bash` |
| **uv** | 0.4+ | 초고속 Python 가상환경 및 패키지 관리자 | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node.js** | 18.0+ | React 프론트엔드 빌드 및 개발 서버 | `brew install node` | `nvm install 20` |

#### macOS 원클릭 일괄 설치 (Homebrew):
```bash
brew install k3d kubectl helm uv node
```

#### Windows (WSL2 / Winget):
```powershell
winget install Docker.DockerDesktop Rancher.k3d Kubernetes.kubectl Helm.Helm astral-sh.uv OpenJS.NodeJS
```

---

### 2.3 KEDA ScaledJob 스케일링 설정 (`deploy/kubernetes/manifests/scaledjob.yaml`)

KEDA는 PostgreSQL의 대기 질문 및 작업 큐를 주기적으로 폴링(3s)하여 Worker Pod를 0개에서 최대 16개(시스템 자원 비례)까지 자동 증설합니다:

- **`workflow-core-scaler`**: `workflow_runs` 테이블의 `status = 'queued'` 건수에 따라 워커 확장.
- **`bi-materialization-scaler`**: `bi_materialization_jobs` 테이블의 `status = 'queued'` 건수 기반 확장.
- **`bi-question-scaler`**: `bi_questions` 테이블의 대기 질문(`status = 'queued'`) 건수 기반 대규모 병렬 추출 확장 (ScaleTarget: 16).
- **`benchmark-scaler`**: `benchmark_runs` 테이블의 `status = 'queued'` 평가 작업 기반 확장.

```yaml
# ScaledJob 매니페스트 예시 (bi-question 워커)
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata:
  name: bi-question-worker
  namespace: bist-batch
spec:
  jobTargetRef:
    template:
      spec:
        containers:
          - name: worker
            image: bist-workflow-worker:local
            command: ["python", "-m", "backend.features.bi.question_worker_main"]
            envFrom:
              - secretRef:
                  name: bist-secrets
  pollingInterval: 3
  successfulJobsHistoryLimit: 5
  failedJobsHistoryLimit: 5
  maxReplicaCount: 16
  triggers:
    - type: postgresql
      metadata:
        connectionFromEnv: PGVECTOR_URL
        query: "SELECT COUNT(*) FROM bi_questions WHERE status = 'queued'"
        targetQueryValue: "16"
```

---

## 3. 로컬 서비스 실행 가이드

### 3.1 환경 변수 설정 (`.env`)
루트 디렉토리에 `.env` 파일을 구성합니다:

```env
OPENAI_API_KEY=sk-proj-your-api-key-here
PGVECTOR_URL=postgresql://postgres:postgres@localhost:5432/rag_flow
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 3.2 의존성 설치
```bash
# Python 백엔드 및 모듈 의존성 설치
uv sync --frozen

# Frontend 의존성 설치
cd frontend
npm ci
cd ..
```

### 3.3 서버 기동
```bash
# Terminal 1: Backend FastAPI Control Plane
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload

# Terminal 2: Frontend React UI
cd frontend
npm run dev
```

- **웹 대시보드 UI**: [http://localhost:5173](http://localhost:5173)
- **FastAPI OpenAPI 문서**: [http://localhost:8765/docs](http://localhost:8765/docs)

---

### 3.4 테스트 및 품질 검증

```bash
# 백엔드 Python 테스트 & 린트
uv run pytest tests/
uv run ruff check modules backend jobs tests
uv run pyright

# 프론트엔드 테스트 & 빌드
cd frontend
npm test
npm run build
```

---

## 4. (선택 사항) 로컬 pgvector 컨테이너 및 Docker 단독 빌드

> [!NOTE]
> **외부 PostgreSQL / 클라우드 DB(Supabase, Neon, RDS 등)를 사용하거나 이미 로컬에 실행 중인 DB가 있다면 본 섹션은 건너뛰셔도 무방합니다.**  
> `.env`의 `PGVECTOR_URL`에 해당 DB 주소만 적어주시면 `./deploy/kubernetes/local.sh`가 이를 자동 감지하여 처리합니다.

### 4.1 로컬 PostgreSQL + pgvector 컨테이너 설정 (`deploy/compose/docker-compose.yml`)

로컬에 pgvector가 설치되어 있지 않거나 독립된 로컬 전용 DB 컨테이너가 필요한 경우 사용합니다.

```yaml
services:
  pgvector:
    image: pgvector/pgvector:pg16
    container_name: bist-pgvector
    restart: unless-stopped
    shm_size: 4g
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-rag_flow}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    ports:
      - "0.0.0.0:${PGVECTOR_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    command:
      - "postgres"
      - "-c", "listen_addresses=*"
      - "-c", "shared_buffers=4GB"
      - "-c", "work_mem=64MB"
      - "-c", "maintenance_work_mem=1GB"
      - "-c", "effective_cache_size=8GB"
      - "-c", "max_parallel_workers_per_gather=4"
      - "-c", "max_parallel_maintenance_workers=4"
      - "-c", "max_parallel_workers=8"
      - "-c", "effective_io_concurrency=200"
      - "-c", "random_page_cost=1.1"
      - "-c", "wal_buffers=64MB"
      - "-c", "min_wal_size=1GB"
      - "-c", "max_wal_size=4GB"
      - "-c", "max_connections=200"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-rag_flow}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
    external: true
```

#### 로컬 pgvector 컨테이너 기동:
```bash
# 1. 외장 볼륨 생성 (데이터 영속성 보장)
docker volume create pgdata

# 2. pgvector 컨테이너 시작
docker compose -f deploy/compose/docker-compose.yml up -d

# 3. 컨테이너 상태 및 헬스체크 확인
docker compose -f deploy/compose/docker-compose.yml ps
```

### 4.2 Docker 이미지 수동 빌드 (`deploy/docker/`)

```bash
# Backend Control Plane 이미지 빌드
docker build -t bist-backend:local -f deploy/docker/Dockerfile.backend .

# Kubernetes / Worker 이미지 빌드
docker build -t bist-workflow-worker:local -f deploy/docker/Dockerfile.worker .

# Frontend UI 이미지 빌드
docker build -t bist-frontend:local -f deploy/docker/Dockerfile.frontend ./frontend
```

---

## 5. 디렉토리 구조

```text
bist-mini-final/
├── modules/                       # RAG 파이프라인 단일 소스 모듈 (Retriever, Expander, Reader 등)
├── jobs/                          # canonical DAG 파이프라인 및 배치 엔트리포인트
├── backend/
│   ├── api/                       # FastAPI 라우트, 스키마, SSE 스트리밍
│   ├── bootstrap/                 # 의존성 주입 컨테이너
│   ├── engine/                    # DAG 실행 엔진 및 워커
│   ├── features/
│   │   ├── bi/                    # BI 카탈로그, 질문 생성기, 공식 계산기, 스냅샷
│   │   └── benchmark/             # RAG 벤치마크 및 지표 평가
│   └── storage/                   # PostgreSQL 커넥션 풀, pgvector 저장소
├── frontend/                      # React 18, TypeScript, TailwindCSS, Recharts
├── deploy/
│   ├── compose/                   # Docker Compose (pgvector 전용 인프라)
│   ├── docker/                    # Dockerfiles (backend, worker, frontend)
│   └── kubernetes/                # k3d 스크립트, KEDA ScaledJob 매니페스트
└── docs/specs/                    # 아키텍처 및 검증 명세서
```
