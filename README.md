# BIST Mini Final

재무 스프레드시트 구조 분석, 외부 vision 기반 테이블 감지, PostgreSQL/pgvector 하이브리드 검색(Dense + FTS + RRF), 셀 근거 기반 응답, BI 대시보드·기업 비교와 RAG 벤치마크를 제공하는 Excel RAG 플랫폼입니다.

이 문서는 저장소를 처음 받은 개발자가 **로컬 웹 애플리케이션을 실행하고, 필요할 때 k3d/KEDA 워커까지 구성**할 수 있도록 현재 프로젝트 설정을 기준으로 작성되었습니다.

## 1. 실행 환경

| 도구 | 지원/권장 버전 | 용도 |
| --- | --- | --- |
| Python | 3.11 이상, **3.12 권장** | FastAPI, 파이프라인, 워커 |
| uv | 최신 안정 버전 | Python 가상환경 및 잠금 의존성 설치 |
| Node.js | **22 LTS 권장** | React/Vite 프론트엔드 |
| npm | Node.js에 포함 | 프론트엔드 의존성 및 스크립트 |
| Docker | 24 이상 권장 | PostgreSQL/pgvector, 이미지 빌드 |
| Git | 최신 안정 버전 | 소스 관리 |

전체 비동기 실행 환경에는 `k3d`, `kubectl`, `helm`이 추가로 필요합니다. Windows에서는 WSL2 또는 Git Bash에서 `deploy/kubernetes/local.sh`를 실행할 수 있습니다. 스크립트는 Device Guard가 프로젝트 가상환경 실행을 막는 경우 uv 관리 Python으로 자동 우회합니다.

> 로컬 pgvector 설정은 `shared_buffers=4GB`를 사용합니다. Docker Desktop에는 메모리를 8GB 이상 할당하는 것을 권장하며, 자원이 부족한 환경에서는 `deploy/compose/docker-compose.yml`의 PostgreSQL 메모리 설정을 낮춰야 합니다.

설치 여부는 저장소를 구성하기 전에 확인합니다.

```bash
python --version
uv --version
node --version
npm --version
docker version
```

## 2. 빠른 시작: 백엔드 + 프론트엔드

아래 구성은 개발 서버와 PostgreSQL을 실행합니다. 파일 업로드, BI 생성, 벤치마크처럼 큐에 등록되는 작업을 실제 처리하려면 [5. 비동기 워커 실행](#5-비동기-워커-실행)도 구성해야 합니다.

### 2.1 환경 변수 파일 만들기

저장소 루트에서 실행합니다.

PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS, Linux, WSL2:

```bash
cp .env.example .env
```

`.env`에서 데이터베이스 주소를 확인하고, OpenAI 기반 모듈을 사용한다면 API 키를 입력합니다.

```dotenv
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
PGVECTOR_URL=postgresql://postgres:postgres@localhost:5432/rag_flow
# Multi-Pod SSE relay is optional for a single local API process.
REDIS_URL=
```

백엔드는 API 키 없이도 시작되지만 Query Decomposer, Luna 구조 감지, BI 질문 처리 등 OpenAI를 호출하는 기능은 실패합니다. `.env`와 `frontend/.env*`는 Git에서 제외되어 있으므로 실제 키를 커밋하지 마세요.

### 2.2 PostgreSQL + pgvector 실행

현재 Docker Compose 파일은 **데이터베이스만** 실행하며 외부 Docker 볼륨 `pgdata`를 사용합니다.

```bash
docker volume create pgdata
docker compose -f deploy/compose/docker-compose.yml up -d
docker compose -f deploy/compose/docker-compose.yml ps
```

`bist-pgvector`의 상태가 `healthy`인지 확인합니다. 외부 PostgreSQL을 사용한다면 이 단계는 건너뛰고 `.env`의 `PGVECTOR_URL` 또는 `DATABASE_URL`을 해당 접속 문자열로 설정합니다. 최초 실행과 배포 전에는 버전 마이그레이션을 적용합니다.

```bash
uv run alembic upgrade head
```

기존 설치도 `CREATE IF NOT EXISTS` 기반 기준선으로 현재 데이터를 유지한 채 채택됩니다. 애플리케이션의 시작 시 스키마 확인은 이전 배포와의 호환 안전망이며, 이후 스키마 변경은 `migrations/`의 새 Alembic revision으로 추가합니다.

### 2.3 의존성 설치

```bash
uv sync --frozen
npm --prefix frontend ci
```

`uv sync --frozen`은 루트의 `uv.lock`을 그대로 사용해 Python 개발 의존성까지 설치합니다.

### 2.4 개발 서버 실행

터미널 1 — FastAPI 백엔드:

```bash
uv run uvicorn backend.entrypoints.asgi:app --host 0.0.0.0 --port 8765 --reload
```

터미널 2 — React/Vite 프론트엔드:

```bash
npm --prefix frontend run dev
```

접속 주소:

| 서비스 | 주소 |
| --- | --- |
| 웹 UI | <http://localhost:5173> |
| Swagger UI | <http://localhost:8765/docs> |
| ReDoc | <http://localhost:8765/redoc> |
| OpenAPI JSON | <http://localhost:8765/openapi.json> |
| 상태 확인 | <http://localhost:8765/healthz> |
| Liveness | <http://localhost:8765/livez> |
| 준비 상태 | <http://localhost:8765/readyz> |
| Kubernetes 작업 관제 | <http://localhost:5173/jobs> |

프론트엔드 개발 서버는 `/api`, `/docs`, `/redoc`, `/openapi.json` 요청을 `http://localhost:8765`로 프록시합니다. 정식 API 경로는 `/api/v1`이며 기존 `/api` 경로도 호환용으로 유지됩니다.

### 2.5 기동 확인

PowerShell:

```powershell
Invoke-RestMethod http://localhost:8765/healthz
Invoke-RestMethod http://localhost:8765/readyz
```

macOS, Linux, WSL2:

```bash
curl http://localhost:8765/healthz
curl http://localhost:8765/readyz
```

`/healthz`는 프로세스 생존 여부, `/readyz`는 데이터베이스를 포함한 요청 처리 준비 상태를 확인합니다.

## 3. 환경 변수

### 애플리케이션 설정

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 없음 | OpenAI 기반 모듈 사용 시 필요 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 호환 API 주소 |
| `DATABASE_URL` | 없음 | 설정하면 `PGVECTOR_URL`보다 우선하는 PostgreSQL 접속 문자열 |
| `PGVECTOR_URL` | `postgresql://postgres:postgres@localhost:5432/rag_flow` | PostgreSQL/pgvector 및 큐 저장소 주소 |
| `REDIS_URL` | 없음 | 설정 시 API Pod 간 SSE 상태 변경 알림용 Redis Pub/Sub 주소. 상태 원본은 계속 PostgreSQL이며 Redis 장애 시 0.5초 폴링으로 안전하게 대체 |
| `USE_PGVECTOR` | `true` | `true`, `1`, `yes`일 때 pgvector 사용 |
| `DB_POOL_MIN_SIZE` | `2` | 백엔드 프로세스의 최소 DB 연결 수 |
| `DB_POOL_MAX_SIZE` | 템플릿 `10`, 미설정 시 `50` | 백엔드 프로세스의 최대 DB 연결 수 |
| `KUBERNETES_WORKFLOW_QUEUE` | `workflow-core` | 기본 워크플로 큐 이름 |
| `KUBERNETES_DATABASE_URL` | 없음 | Kubernetes 배포에만 사용할 PostgreSQL 접속 문자열. 지정하면 `DATABASE_URL`, `PGVECTOR_URL`보다 우선 |
| `KUBERNETES_BACKEND_IMAGE` | `bist-backend:local` | 배포할 API 이미지. 레지스트리 태그를 지정할 수 있음 |
| `KUBERNETES_WORKER_IMAGE` | `bist-workflow-worker:local` | 배포할 KEDA 워커 이미지 |
| `KUBERNETES_FRONTEND_IMAGE` | `bist-frontend:local` | 배포할 UI 이미지 |
| `K3D_IMPORT_IMAGES` | `true` | `true`면 로컬 빌드 이미지를 k3d에 import. 원격 레지스트리 배포 시 `false` |
| `KUBERNETES_MAX_JOBS` | 자동 계산 | k3d/KEDA 최대 병렬 Job 수. 빈 값이면 Docker 자원으로 계산 |
| `KUBERNETES_JOB_CPU_REQUEST` | `1000m` | 워커 CPU request |
| `KUBERNETES_JOB_MEMORY_REQUEST` | `2Gi` | 워커 메모리 request |
| `KUBERNETES_JOB_CPU_LIMIT` | `2` | 워커 CPU limit |
| `KUBERNETES_JOB_MEMORY_LIMIT` | `3Gi` | 워커 메모리 limit |
| `INGESTION_SHARDS_ENABLED` | `false` | 직접 실행 시 분산 Excel ingestion 사용 여부. Kubernetes ScaledJob 템플릿은 `true`를 주입 |
| `INGESTION_SHARD_POLL_SECONDS` | `1` | 부모 ingestion 모듈의 child shard 상태 조회 간격 |
| `INGESTION_SHARD_WAIT_TIMEOUT_SECONDS` | `21000` | embedding/COPY shard barrier 최대 대기 시간 |
| `INGESTION_VECTOR_SHARD_SIZE` | `4096` | 한 vector COPY Job이 담당하는 문서 수 |
| `BI_QUESTION_BATCH_SIZE` | `16` | BI 질문 워커가 한 번에 가져올 질문 수 |
| `BI_QUESTION_MAX_WORKERS` | `4` | BI 질문 워커 내부 최대 병렬 스레드 수 |
| `LOG_LEVEL` | `INFO` | 워커 로그 레벨 |

`KUBERNETES_JOB_NAME`은 Kubernetes가 워커 식별용으로 주입하는 값이고, `WORKFLOW_QUEUE`는 워크플로 워커 프로세스에서 기본 큐를 일시적으로 재정의할 때 사용합니다.

### Docker Compose 설정

다음 값은 `deploy/compose/docker-compose.yml`의 PostgreSQL 컨테이너 설정에 사용됩니다.

| 변수 | 기본값 |
| --- | --- |
| `POSTGRES_DB` | `rag_flow` |
| `POSTGRES_USER` | `postgres` |
| `POSTGRES_PASSWORD` | `postgres` |
| `PGVECTOR_PORT` | `5432` |

기본 계정 정보는 로컬 개발용입니다. 공유 환경이나 운영 환경에서는 반드시 별도 비밀번호와 Secret 저장소를 사용하세요.

## 4. 외부 데이터베이스 사용

PostgreSQL 16과 pgvector 확장을 사용할 수 있는 관리형 DB(Supabase, Neon, RDS 등)도 연결할 수 있습니다.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

- `DATABASE_URL`이 있으면 `PGVECTOR_URL`보다 우선합니다.
- 접속 계정에는 확장 및 스키마를 준비할 권한이 필요합니다.
- 특수문자가 포함된 사용자명과 비밀번호는 URL 인코딩해야 합니다.
- `deploy/kubernetes/local.sh`는 `KUBERNETES_DATABASE_URL` → `DATABASE_URL` → `PGVECTOR_URL` 순으로 클러스터 DB를 선택합니다. 개발용 `.env`가 원격 DB를 가리키더라도, 로컬 k3d 실행에만 `KUBERNETES_DATABASE_URL`을 지정해 분리할 수 있습니다.
- 원격 DB를 선택한 경우 스크립트는 마이그레이션이나 기존 로컬 PostgreSQL 컨테이너 중지 전에 인증 연결과 `SELECT 1`을 확인합니다. 검증에 실패하면 기존 로컬 DB와 클러스터를 유지한 채 중단합니다.

## 5. 비동기 워커 실행

이 프로젝트의 워크플로, BI, 벤치마크는 PostgreSQL 큐와 one-shot 워커를 사용합니다.

```text
React/Vite → FastAPI → PostgreSQL 큐 → KEDA ScaledJob → Worker Pod
```

### 5.1 전체 로컬 배치 환경: k3d + KEDA

Docker가 실행 중인 macOS/Linux/WSL2에서 다음 명령을 사용합니다.

```bash
./deploy/kubernetes/local.sh all
./deploy/kubernetes/local.sh status
```

`all`은 도구 확인, Python 동기화, DB 사전 검증·pgvector·Alembic 마이그레이션, k3d 클러스터 생성, KEDA/Metrics Server/NGINX Ingress 설치, API·워커·UI 이미지 빌드 및 import, Redis·전용 KEDA `TriggerAuthentication` Secret·6개 ScaledJob·Deployment·Ingress 배포를 순서대로 수행합니다. 로컬 기본 이미지는 `uv.lock`에 고정된 CPU 애플리케이션 의존성만 설치합니다.

개발용 `.env`의 `DATABASE_URL`이 원격 DB를 가리킬 때 로컬 DB로 실행하려면 다음처럼 한 번만 재정의합니다.

```bash
KUBERNETES_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rag_flow \
  ./deploy/kubernetes/local.sh all
```

단계별 명령:

```bash
./deploy/kubernetes/local.sh setup-tools  # 도구 및 Python 환경 준비
./deploy/kubernetes/local.sh check        # 도구 확인
./deploy/kubernetes/local.sh cluster      # DB, k3d, KEDA 준비
./deploy/kubernetes/local.sh build        # API·워커·UI 이미지 빌드 및 k3d import
./deploy/kubernetes/local.sh deploy       # DB migration, 워커, API/UI/Ingress 적용
./deploy/kubernetes/local.sh recreate     # 8080/8443 포트 매핑을 포함해 k3d만 다시 생성
./deploy/kubernetes/local.sh restart      # 중지된 클러스터 재시작
./deploy/kubernetes/local.sh status       # 용량, Pod, Job, ScaledJob 확인
./deploy/kubernetes/local.sh logs         # 워크플로 워커 로그 확인
./deploy/kubernetes/local.sh logs-api     # API 로그 확인
./deploy/kubernetes/local.sh logs-ingestion # embedding/vector shard 워커 로그 확인
./deploy/kubernetes/local.sh down         # 클러스터 정지(데이터 유지)
./deploy/kubernetes/local.sh destroy      # k3d 클러스터 삭제
```

`recreate`와 `destroy`는 k3d 클러스터만 삭제하며 외부 Docker 볼륨 `pgdata`는 삭제하지 않습니다. 새 클러스터는 `http://localhost:8080`을 Ingress에 연결하고 8443 포트도 예약합니다. 실제 HTTPS는 운영 도메인과 TLS Secret을 설정한 뒤 사용합니다. 이전 형식으로 생성한 클러스터는 안전을 위해 자동 삭제하지 않으므로, 포트가 없다면 `recreate`를 실행하거나 다음처럼 임시 접속합니다.

```bash
kubectl -n bist-batch port-forward service/frontend-ui 8080:80
```

원격 레지스트리로 배포할 때는 이미지를 별도로 `docker push`한 후, import를 끄고 불변 태그를 지정합니다.

```bash
K3D_IMPORT_IMAGES=false \
KUBERNETES_BACKEND_IMAGE=registry.example.com/bist/backend:2026.08.27 \
KUBERNETES_WORKER_IMAGE=registry.example.com/bist/worker:2026.08.27 \
KUBERNETES_FRONTEND_IMAGE=registry.example.com/bist/frontend:2026.08.27 \
  ./deploy/kubernetes/local.sh deploy
```

### 5.2 운영 배포: Helm Chart

운영·스테이징은 [`deploy/helm/bist/`](deploy/helm/bist/) Chart를 기준으로 배포합니다. Secret은 Chart 값에 넣지 않고, 애플리케이션용 `bist-batch-env`와 KEDA PostgreSQL 트리거 전용 `bist-keda-postgresql`을 네임스페이스에 먼저 생성합니다. 운영용 RWX PVC도 `bist-data` 이름으로 사전에 준비해야 합니다.

```bash
kubectl create namespace bist-batch
kubectl -n bist-batch create secret generic bist-batch-env \
  --from-literal=PGVECTOR_URL='postgresql://USER:PASSWORD@HOST:5432/DATABASE' \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
kubectl -n bist-batch create secret generic bist-keda-postgresql \
  --from-literal=PGVECTOR_URL='postgresql://USER:PASSWORD@HOST:5432/DATABASE'
helm upgrade --install bist ./deploy/helm/bist \
  --namespace bist-batch \
  --values ./deploy/helm/bist/values.yaml
```

로컬 k3d 검증용 값은 `values-k3d.yaml`이며, 호스트 경로와 단일 replica를 사용하므로 운영에 사용하지 않습니다. Chart는 Redis, schema migration hook, API/UI deployment, 6개 KEDA ScaledJob 및 `TriggerAuthentication`을 함께 렌더링합니다. Excel ingestion은 부모 workflow 외에 `ingestion-embedding`(최대 4개)과 `ingestion-vector`(최대 2개) child Job을 사용합니다.

### 5.3 워커를 로컬에서 한 번 실행하기

Kubernetes 없이 큐 동작을 디버깅할 때 사용할 수 있습니다. 각 명령은 현재 큐에서 작업을 가져와 한 번 처리한 뒤 종료합니다.

```bash
# workflow-core 큐 1건
uv run python -m backend.entrypoints.worker workflow

# BI materialization 1건
uv run python -m backend.entrypoints.worker bi-materialization

# BI 질문 최대 1 batch
uv run python -m backend.entrypoints.worker bi-question

# benchmark 1건
uv run python -m backend.entrypoints.worker benchmark

# ingestion embedding/vector shard 각각 1건
uv run python -m backend.entrypoints.worker ingestion-embedding
uv run python -m backend.entrypoints.worker ingestion-vector
```

큐가 비어 있으면 정상적으로 메시지를 출력하고 종료합니다. 연속 처리가 필요하면 KEDA 구성을 사용하세요.

## 6. 테스트와 품질 검증

저장소 루트에서 실행합니다.

```bash
# Python
uv run alembic upgrade head
uv run pytest -q
uv run ruff check .
uv run pyright

# Frontend
npm --prefix frontend run check
```

프론트엔드 빌드 결과는 루트의 `dist/`에 생성됩니다.

## 7. Docker 이미지 빌드

세 Dockerfile 모두 저장소 루트를 build context로 사용합니다.

```bash
docker build -t bist-backend:local -f deploy/docker/Dockerfile.backend .
docker build -t bist-workflow-worker:local -f deploy/docker/Dockerfile.worker .
docker build -t bist-frontend:local -f deploy/docker/Dockerfile.frontend .
```

`deploy/compose/docker-compose.yml`은 전체 애플리케이션 Compose 구성이 아니라 pgvector 전용 구성입니다. 백엔드와 프론트엔드는 개발 명령 또는 각 Docker 이미지로 별도 실행합니다.

## 8. 문제 해결

### `uv` 명령을 찾을 수 없음

uv 설치 후 터미널을 다시 열고 확인합니다.

```bash
uv --version
```

Windows에서 이미 `.venv`가 준비되어 있다면 임시로 다음과 같이 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.entrypoints.asgi:app --host 0.0.0.0 --port 8765 --reload
.\.venv\Scripts\python.exe -m pytest -q
```

### DB 연결 실패 또는 `/readyz` 실패

```bash
docker compose -f deploy/compose/docker-compose.yml ps
docker logs bist-pgvector --tail 100
```

- `pgdata` 볼륨이 없으면 `docker volume create pgdata`를 실행합니다.
- 5432 포트가 이미 사용 중이면 `PGVECTOR_PORT`와 애플리케이션 DB URL의 포트를 함께 변경합니다.
- Docker 메모리가 부족하면 Docker Desktop 할당량을 높이거나 Compose의 PostgreSQL 메모리 설정을 낮춥니다.
- 외부 DB 사용 시 방화벽, SSL 옵션, 사용자 권한을 확인합니다.

### 작업이 `queued`에서 진행되지 않음

API와 DB만 실행한 상태에서는 정상적인 현상입니다. `./deploy/kubernetes/local.sh status`로 KEDA 워커를 확인하거나 [로컬 one-shot 워커](#52-워커를-로컬에서-한-번-실행하기)를 실행합니다.

### OpenAI 호출 오류

- `.env`의 `OPENAI_API_KEY`와 `OPENAI_BASE_URL`을 확인합니다.
- 호환 API를 사용할 경우 `/v1` 포함 여부와 지원 모델을 확인합니다.
- 키를 로그, 이슈, 커밋에 남겼다면 즉시 폐기하고 재발급합니다.

### 프론트엔드에서 API 호출 실패

- 백엔드가 `localhost:8765`에서 실행 중인지 확인합니다.
- 프론트엔드는 `npm --prefix frontend run dev`로 실행해야 Vite 프록시 설정을 사용합니다.
- 직접 API를 호출할 때는 정식 경로 `/api/v1`을 사용합니다.

## 9. 프로젝트 구조

```text
bist-mini-final/
├── backend/
│   ├── api/                  # router 결합, 미들웨어, 예외, OpenAPI/SPA/probe
│   ├── bootstrap/            # application object graph와 HTTP/worker lifecycle
│   ├── core/                 # 런타임 환경 설정만 보유
│   ├── domains/              # 7개 bounded context vertical slice
│   ├── entrypoints/          # ASGI·worker·관리 명령 process adapter
│   ├── platform/             # PostgreSQL, pgvector, OpenAI, Redis, K8s adapter
│   └── shared/               # 상태 stream, lease, embedding 등 공통 계약
├── frontend/                 # React 18, TypeScript, Vite
├── modules/                  # RAG 파이프라인 모듈 및 Pydantic 계약
├── jobs/                     # canonical DAG/worker Job 선언과 K8s projection
├── deploy/
│   ├── compose/              # 로컬 pgvector
│   ├── docker/               # backend, worker, frontend 이미지
│   └── kubernetes/           # k3d/KEDA 스크립트와 매니페스트
├── docs/
│   ├── blueprints/           # 시스템·데이터·UI·검증 청사진
│   └── CURRENT_IMPLEMENTATION_BASELINE.md
├── tests/                    # Python 계약 및 통합 테스트
├── .env.example              # 환경 변수 템플릿
├── pyproject.toml            # Python 프로젝트와 도구 설정
├── uv.lock                   # Python 잠금 파일
└── README.md
```

## 10. 아키텍처 요약

```text
[Frontend: React/Vite]
          │ HTTP / SSE
          ▼
[FastAPI Control Plane :8765]
          │
          ├── PostgreSQL + pgvector
          │     ├── workflow queue / leases
          │     ├── BI jobs / questions / answers
          │     └── benchmark runs / results
          │
          └── KEDA PostgreSQL trigger
                    ▼
              [ScaledJob Workers]
```

- `modules/`가 파이프라인 모듈 계약의 단일 소스입니다.
- FastAPI는 요청 검증, 큐 등록, 조회, SSE 관찰을 담당합니다.
- KEDA는 PostgreSQL 큐 길이에 따라 one-shot 워커를 0개부터 확장합니다.
- 상세 설계와 현재 검증 수치는 각각 [`docs/blueprints/`](docs/blueprints/)와 [`docs/CURRENT_IMPLEMENTATION_BASELINE.md`](docs/CURRENT_IMPLEMENTATION_BASELINE.md)를 참고하세요.
