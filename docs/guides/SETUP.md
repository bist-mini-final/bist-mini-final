# 설치·실행·배포 가이드

[프로젝트 소개](../../README.md) · [문서 목차](../README.md) · [협업·품질 관리](COLLABORATION.md)

기준일: 2026-09-07. 모든 명령은 **저장소 루트**에서 실행합니다. 이 문서는 로컬 개발 서버, k3d/KEDA 워커, Helm 배포의 설정과 문제 해결 방법을 다룹니다. 프로젝트 결과와 운영 한계는 [완료 요약](../PROJECT_SUMMARY.md)을 참고하세요.

## 1. 실행 환경

| 도구 | 지원/권장 버전 | 용도 |
| --- | --- | --- |
| Python | 3.11 이상, CI 기준 3.12 | FastAPI, 파이프라인, 워커 |
| uv | CI 기준 0.12.5 | Python 가상환경 및 잠금 의존성 설치 |
| Node.js | CI 기준 20 | React/Vite 프론트엔드 |
| npm | Node.js에 포함 | 프론트엔드 의존성 및 스크립트 |
| Docker | Compose v2 사용 가능 환경 | PostgreSQL/pgvector, 이미지 빌드 |
| Git | Git CLI | 소스 관리 |

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

최초 설치 시 저장소 루트에서 실행합니다. 이미 `.env`가 있다면 복사 명령으로 덮어쓰지 말고 필요한 설정만 확인합니다.

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

### 2.2 의존성 설치

```bash
uv sync --frozen
npm --prefix frontend ci
```

`uv sync --frozen`은 루트의 `uv.lock`을 그대로 사용해 Python 개발 의존성까지 설치합니다.

### 2.3 PostgreSQL + pgvector 실행

현재 Docker Compose 파일은 **데이터베이스만** 실행하며 외부 Docker 볼륨 `pgdata`를 사용합니다.

```bash
docker volume create pgdata
docker compose -f deploy/compose/docker-compose.yml up -d
docker compose -f deploy/compose/docker-compose.yml ps
```

`bist-pgvector`의 상태가 `healthy`인지 확인합니다. 외부 PostgreSQL을 사용한다면 이 단계는 건너뛰고 `.env`의 `PGVECTOR_URL` 또는 `DATABASE_URL`을 해당 접속 문자열로 설정합니다. 최초 실행과 배포 전에는 연결 대상을 확인하고 버전 마이그레이션을 적용합니다. 기존 데이터베이스는 먼저 백업하세요.

```bash
uv run alembic upgrade head
```

기존 설치도 `CREATE IF NOT EXISTS` 기반 기준선으로 현재 데이터를 유지한 채 채택됩니다. 애플리케이션의 시작 시 스키마 확인은 이전 배포와의 호환 안전망이며, 이후 스키마 변경은 `migrations/`의 새 Alembic revision으로 추가합니다.

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
| Swagger UI (개발 전용) | <http://localhost:8765/docs> |
| ReDoc (개발 전용) | <http://localhost:8765/redoc> |
| OpenAPI JSON (개발 전용) | <http://localhost:8765/openapi.json> |
| 상태 확인 | <http://localhost:8765/healthz> |
| Liveness | <http://localhost:8765/livez> |
| 준비 상태 | <http://localhost:8765/readyz> |
| Kubernetes 작업 관제 | <http://localhost:5173/jobs> |

프론트엔드 개발 서버는 `/api`만 `http://localhost:8765`로 프록시합니다. API 명세는 프론트엔드와 외부 Ingress를 경유하지 않고 개발 환경의 백엔드 포트에서만 확인합니다. 정식 API 경로는 `/api/v1`이며 기존 `/api` 경로도 호환용으로 유지됩니다.

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
| `APP_ENV` | `development` | `production` 또는 `prod`이면 API 명세 비공개가 기본값 |
| `EXPOSE_API_DOCS` | 개발 `true`, 운영 `false` | Swagger, ReDoc, OpenAPI JSON 공개 여부. 운영 배포에서는 명시적으로 `false` 사용 |
| `AUTH_ENABLED` | `false` | 서명 세션 인증과 API RBAC 활성화. 공유·운영 배포에서는 반드시 `true` |
| `AUTH_USERS_JSON` | 없음 | `username`, PBKDF2 `password_hash`, `role`, `tenant_id`를 가진 사용자 배열. 평문 비밀번호를 저장하지 않음 |
| `AUTH_SESSION_SECRET` | 없음 | 세션 서명용 32자 이상 비밀값. 운영 Secret에서 주입하고 정기 교체 |
| `AUTH_SESSION_TTL_SECONDS` | `28800` | 로그인 세션 유효 시간(300~86400초) |
| `AUTH_COOKIE_SECURE` | 운영 `true` | HTTPS에서만 세션 쿠키 전송. HTTP 전용 로컬 k3d는 `false` |
| `USE_PGVECTOR` | `true` | `true`, `1`, `yes`일 때 pgvector 사용 |
| `DB_POOL_MIN_SIZE` | `2` | 백엔드 프로세스의 최소 DB 연결 수 |
| `DB_POOL_MAX_SIZE` | 템플릿 `10`, 미설정 시 `50` | 백엔드 프로세스의 최대 DB 연결 수 |
| `KUBERNETES_WORKFLOW_QUEUE` | `workflow-core` | 기본 워크플로 큐 이름 |
| `KUBERNETES_DATABASE_URL` | 없음 | Kubernetes 배포에만 사용할 PostgreSQL 접속 문자열. 지정하면 `DATABASE_URL`, `PGVECTOR_URL`보다 우선 |
| `KUBERNETES_BACKEND_IMAGE` | `bist-backend:<git-sha>` | 배포할 API 이미지. 작업 트리가 더러우면 추적·신규 소스의 내용 지문을 포함한 `-dirty-<hash>`가 붙음 |
| `KUBERNETES_WORKER_IMAGE` | `bist-workflow-worker:<git-sha>` | 배포할 KEDA 워커 이미지 |
| `KUBERNETES_FRONTEND_IMAGE` | `bist-frontend:<git-sha>` | 배포할 UI 이미지 |
| `K3D_IMPORT_IMAGES` | `true` | `true`면 로컬 빌드 이미지를 k3d에 import. 원격 레지스트리 배포 시 `false` |
| `KUBERNETES_MAX_JOBS` | 자동 계산 | k3d/KEDA 최대 병렬 queue slot 수. 빈 값이면 Docker 자원과 parent/child Pod 쌍의 총 request로 계산 |
| `KUBERNETES_CAPACITY_CPU_PER_SLOT` | `2` | 자동 계산에서 queue slot 하나(benchmark/ingestion parent와 workflow child)의 합산 CPU request |
| `KUBERNETES_CAPACITY_MEMORY_GIB_PER_SLOT` | `4` | 자동 계산에서 queue slot 하나의 합산 메모리 request(GiB) |
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
./deploy/kubernetes/local.sh credentials
```

첫 배포는 `bist-auth-env`에 PBKDF2 비밀번호 해시와 세션 서명 키를 생성하고,
초기 관리자 자격 증명은 별도 `bist-auth-bootstrap` Secret에 보관합니다.
`credentials` 명령으로 확인한 뒤 공유 환경에서는 bootstrap Secret을 삭제하고
조직의 Secret 관리자와 계정 수명주기 정책으로 교체하세요. HTTP 로컬 배포 외에는
`AUTH_COOKIE_SECURE=true`와 유효한 TLS 인증서가 필수입니다.

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

Windows Git Bash에서는 MSYS가 k3d volume 인자의 컨테이너 경로를 Windows 경로로 바꾸지 않도록 `local.sh`가 `cygpath`와 `MSYS_NO_PATHCONV`를 적용합니다. 재생성·삭제 시에는 PostgreSQL 컨테이너를 기존 k3d 네트워크에서 먼저 분리해 stale network를 방지하고, 새 클러스터가 준비되면 자동으로 다시 연결합니다. DB 컨테이너와 데이터 volume은 삭제하지 않습니다. `bash`가 WSL relay를 가리키면서 `/bin/bash`를 찾지 못하는 PC에서는 `C:\Program Files\Git\bin\bash.exe deploy/kubernetes/local.sh ...`처럼 Git Bash 실행 파일을 명시합니다.

### 공유기 외부 접속

클러스터를 `recreate`한 뒤 공유기에서 TCP `외부 8080 → Kubernetes 호스트의 고정 LAN IP:8080`을 설정하면 `http://<외부-호스트>:8080`으로 Ingress에 접근할 수 있습니다. SPA와 `/api/*` 요청은 같은 Ingress를 통과하므로 프론트 개발 포트나 backend `8765`를 별도로 공개하지 않습니다. 현재 호스트 주소를 공유기의 DHCP 예약으로 고정하고 Windows 방화벽 인바운드 TCP 8080 허용, DDNS의 공인 IP 일치, 이중 NAT·CGNAT 여부도 함께 확인해야 합니다. 외부 포트 80을 내부 8080으로 전달하면 URL에서 `:8080`을 생략할 수 있습니다.

관리자 PowerShell에서 Private 네트워크용 방화벽 규칙을 한 번 등록합니다.

```powershell
New-NetFirewallRule -DisplayName "Excel RAG k3d Ingress HTTP 8080" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Private
```

검증은 먼저 호스트에서 `http://localhost:8080`, 같은 LAN의 다른 장치에서 `http://<고정-LAN-IP>:8080`, 마지막으로 Wi-Fi를 끈 휴대전화 데이터에서 `http://<외부-호스트>:8080` 순서로 수행합니다. 일부 공유기는 NAT loopback을 지원하지 않아 같은 LAN에서 DDNS 주소로 접속할 때만 timeout이 발생할 수 있습니다.

일반 HTTP 원격 origin은 브라우저의 secure context가 아니므로 `crypto.randomUUID()`가 제공되지 않을 수 있습니다. 프론트의 client-side 식별자는 공통 UUID 유틸에서 `crypto.getRandomValues()` 기반 폴백을 사용합니다. 이는 브라우저 호환 조치일 뿐 전송 구간을 암호화하지 않으므로, 공개 서비스의 HTTPS 요구사항을 대체하지 않습니다.

> **보안 경계:** 운영 API는 `APP_ENV=production`, `EXPOSE_API_DOCS=false`로 기동하며 Ingress/Nginx도 `/docs`, `/redoc`, `/openapi.json`과 내부 probe 경로를 외부에 라우팅하지 않습니다. 공유 k3d 배포는 PBKDF2 계정, 서명 HttpOnly 세션, viewer/operator/admin RBAC와 단일 tenant 경계를 자동 활성화합니다. API에는 보안 응답 헤더를, Ingress에는 연결·요청 속도 제한과 표준 `429` 응답을 적용합니다. Excel 업로드는 buffering 없이 application으로 전달되고 `.xlsx`/`.xlsm` Open XML 구조와 500 MiB 상한을 검증합니다. 8443은 예약 포트일 뿐 TLS 인증서가 자동 구성되는 것은 아닙니다. 인터넷 공개 전에는 유효 인증서, 외부 443 forwarding, `AUTH_COOKIE_SECURE=true`, HTTP→HTTPS redirect를 함께 구성하세요.

원격 레지스트리로 배포할 때는 이미지를 별도로 `docker push`한 후, import를 끄고 불변 태그를 지정합니다. 아래 `<release-tag>`는 실제 빌드한 이미지 태그로 바꿉니다.

```bash
K3D_IMPORT_IMAGES=false \
KUBERNETES_BACKEND_IMAGE='registry.example.com/bist/backend:<release-tag>' \
KUBERNETES_WORKER_IMAGE='registry.example.com/bist/worker:<release-tag>' \
KUBERNETES_FRONTEND_IMAGE='registry.example.com/bist/frontend:<release-tag>' \
  ./deploy/kubernetes/local.sh deploy
```

### 5.2 운영 배포: Helm Chart

운영·스테이징 배포 구성은 [`deploy/helm/bist/`](../../deploy/helm/bist/) Chart를 기준으로 배포합니다. Secret은 Chart 값에 넣지 않고, 애플리케이션용 `bist-batch-env`와 KEDA PostgreSQL 트리거 전용 `bist-keda-postgresql`을 네임스페이스에 먼저 생성합니다. 인증용 `bist-auth-env` Secret에는 `AUTH_ENABLED=true`, PBKDF2 해시를 가진 `AUTH_USERS_JSON`, 32자 이상 `AUTH_SESSION_SECRET`, `AUTH_COOKIE_SECURE=true`가 필요합니다. 운영용 RWX PVC도 `bist-data` 이름으로 사전에 준비해야 합니다. 아래 명령만으로 인터넷 공개 준비가 완료되지는 않습니다. 이미지 태그, 도메인, `ingress.tls`, 인증 Secret은 배포 환경에 맞게 먼저 구성하세요.

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

저장소 루트에서 실행합니다. 전체 백엔드 테스트는 PostgreSQL 연결과 마이그레이션된 스키마를 전제로 하므로 운영 DB가 아닌 별도 테스트 DB를 사용하세요. CI의 PostgreSQL·Redis 구성과 통합 테스트 변수는 [협업·품질 관리](COLLABORATION.md)를 참고하세요.

```bash
# Python
uv run pytest -q
uv run ruff check modules backend jobs tests
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

API와 DB만 실행한 상태에서는 정상적인 현상입니다. `./deploy/kubernetes/local.sh status`로 KEDA 워커를 확인하거나 [로컬 one-shot 워커](#53-워커를-로컬에서-한-번-실행하기)를 실행합니다.

### OpenAI 호출 오류

- `.env`의 `OPENAI_API_KEY`와 `OPENAI_BASE_URL`을 확인합니다.
- 호환 API를 사용할 경우 `/v1` 포함 여부와 지원 모델을 확인합니다.
- 키를 로그, 이슈, 커밋에 남겼다면 즉시 폐기하고 재발급합니다.

### 프론트엔드에서 API 호출 실패

- 백엔드가 `localhost:8765`에서 실행 중인지 확인합니다.
- 프론트엔드는 `npm --prefix frontend run dev`로 실행해야 Vite 프록시 설정을 사용합니다.
- 직접 API를 호출할 때는 정식 경로 `/api/v1`을 사용합니다.
