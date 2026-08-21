# RAG Flow Workbench

재무 질문 처리 모듈을 캔버스에서 조합하고, 사용자가 만든 DAG를 배치 단위로 실행하는 FastAPI + React 애플리케이션입니다.

---

## 목차

1. [새 환경 설치](#새-환경-설치)
2. [선택 데이터 및 로컬 모델](#선택-데이터-및-로컬-모델)
3. [개발 서버 실행](#개발-서버-실행)
4. [운영·문제 해결 명령](#운영문제-해결-명령)
5. [프로젝트 구조](#프로젝트-구조)
6. [모듈 실행 계약](#모듈-실행-계약)
7. [스프레드시트 파이프라인](#스프레드시트-파이프라인)
8. [워크플로 저장 형식](#워크플로-저장-형식)
9. [배치 DAG 실행과 상태 전달](#배치-dag-실행과-상태-전달)
10. [API 레퍼런스](#api-레퍼런스)
11. [개발 문서 관리](#개발-문서-관리)

---

## 새 환경 설치 및 빠른 시작 가이드 (Environment Setup Guide)

본 프로젝트는 **FastAPI 백엔드 + React 프론트엔드 + PostgreSQL 16 pgvector DB + 로컬 Kubernetes (k3d + KEDA ScaledJob)** 기반으로 동작합니다.
대용량 Excel 파싱 및 임베딩과 같은 장시간 배치 작업은 API 프로세스를 블로킹하지 않고, DB 작업 큐에 인큐되어 **KEDA ScaledJob**을 통해 일회성(one-shot) Kubernetes Pod에서 격리 실행됩니다.

---

### 1. 필수 요구 도구 (Prerequisites)

| 도구 | 권장 버전 | 용도 | 필수 여부 |
|---|---:|---|:---:|
| **Git** | 최신 버전 | 소스 코드 버전 관리 | 필수 |
| **Python** | 3.11 이상 (3.11 ~ 3.13) | FastAPI 백엔드, RAG 파이프라인, 테스트 | 필수 |
| **Node.js** | 20 LTS 이상 (npm 10+) | React 프론트엔드 캔버스 개발 및 빌드 | 필수 |
| **Docker & Compose** | Docker Desktop (또는 Docker Engine) | PostgreSQL pgvector 컨테이너 및 k3d 노드 구동 | 필수 |
| **k3d** | 5.9 이상 | 로컬 경량 Kubernetes (k3s) 클러스터 프로비저닝 | 필수 (배치용) |
| **kubectl** | 최신 안정 버전 | Kubernetes 리소스 및 Pod/Job 제어 | 필수 (배치용) |
| **Helm 3** | 최신 안정 버전 | KEDA (Kubernetes Event-driven Autoscaling) 패키지 설치 | 필수 (배치용) |

> [!TIP]
> **Docker Desktop 리소스 권장 사양**: 최소 8GB RAM (12~16GB RAM 권장).
> 설치 스크립트(`setup.sh`)가 Docker 시스템 자원을 자동 감지하여 최적의 최대 병렬 Job 수를 산정합니다.

설치 확인 명령:
```bash
git --version
node --version
docker version
docker compose version
k3d version
kubectl version --client
helm version
```

---

### 2. 저장소 복제 및 환경 변수 설정

```bash
git clone <REPOSITORY_URL> bist-mini-final
cd bist-mini-final
[ -f .env ] || cp .env.example .env
```

`.env` 파일에 API 키와 접속 정보를 입력합니다:

```dotenv
# [필수] OpenAI API Key (Decomposer, Reader, text-embedding-3-large, LLM Judge 등)
OPENAI_API_KEY=sk-proj-...
OPENAI_BASE_URL=https://api.openai.com/v1

# [기본값] 로컬 PostgreSQL pgvector 연결 주소
PGVECTOR_URL=postgresql://postgres:postgres@localhost:5432/rag_flow
USE_PGVECTOR=true

# [선택] 로컬 Kubernetes 배치 워커 설정 (비워둘 시 Docker 자원에 맞춰 자동 계산)
KUBERNETES_INGESTION_QUEUE=excel-ingestion
KUBERNETES_MAX_JOBS=
KUBERNETES_JOB_CPU_REQUEST=1000m
KUBERNETES_JOB_MEMORY_REQUEST=2Gi
KUBERNETES_JOB_CPU_LIMIT=2
KUBERNETES_JOB_MEMORY_LIMIT=3Gi
```

---

### 3. 원클릭 자동 설치 스크립트 실행 (권장)

저장소 루트의 설치 스크립트를 실행하면 **Python 가상환경, npm 의존성, pgvector DB, k3d 클러스터, KEDA 2.20.2, 워커 컨테이너 빌드 및 ScaledJob 배포**까지 한 번에 완료됩니다.

```bash
# macOS / Linux / WSL2
./setup.sh

# Windows (WSL2 + Docker Desktop 환경)
setup.bat
```

---

### 4. 단계별 수동 설치 가이드 (선택)

`setup.sh` 스크립트를 사용하지 않고 직접 수동으로 구성하려면 아래 순서대로 진행합니다.

#### 4-1. Python 가상환경 및 의존성 설치
```bash
# uv 사용 시 (권장 - 빠른 빌드)
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 표준 venv 사용 시
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4-2. 프론트엔드 의존성 설치
```bash
cd frontend
npm ci
cd ..
```

#### 4-3. PostgreSQL pgvector 컨테이너 구동
```bash
docker compose -f docker-compose.db.yml up -d
docker compose -f docker-compose.db.yml ps
```

#### 4-4. Kubernetes 배치 인프라 (k3d + KEDA + ScaledJob) 구성
```bash
# 사전 환경 체크
./deploy/kubernetes/local.sh check

# 클러스터 생성, KEDA 설치, Metrics Server 배포, 워커 이미지 빌드 및 ScaledJob 적용
./deploy/kubernetes/local.sh all

# 클러스터 상태 확인
./deploy/kubernetes/local.sh status
kubectl get scaledjobs,jobs,pods -n bist-batch
```

---

### 5. 개발 서버 실행

서버 구동 시 **FastAPI 백엔드**와 **React 프론트엔드**를 각각 별도 터미널에서 실행합니다.

**터미널 1 — FastAPI 백엔드 (포트 8765):**
```bash
source .venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 8765 --reload
```

**터미널 2 — React 프론트엔드 (포트 5173):**
```bash
cd frontend
npm run dev
```

**접속 주소 안내:**

| 서비스 | URL | 설명 |
|---|---|---|
| **Workbench 웹 UI** | `http://127.0.0.1:5173` | 대화형 모듈 캔버스 및 데이터 소스 관리 화면 |
| **FastAPI Swagger API** | `http://127.0.0.1:8765/docs` | 백엔드 REST API 인터랙티브 문서 |
| **K8s 클러스터 상태** | `./deploy/kubernetes/local.sh status` | KEDA ScaledJob 및 배치 Pod 상태 확인 |

---

### 6. 설치 및 동작 검증 (Verification)

```bash
# 1) 백엔드 모듈 및 DB 상태 검증
curl -fsS http://127.0.0.1:8765/api/modules | grep -o '"type":' | wc -l
curl -fsS http://127.0.0.1:8765/api/data-sources/db-status

# 2) 전체 백엔드 단위/통합 테스트 (197개 테스트)
pytest tests/

# 3) 프론트엔드 빌드 및 테스트
cd frontend && npm run build && npm test -- --run && cd ..
```

---

## 선택 데이터 및 로컬 모델 (선택 - Optional)

> [!NOTE]
> 기본 워크플로는 **OpenAI API (`gpt-5.6-luna`, `text-embedding-3-large`)**를 기본 엔진으로 사용합니다. 아래 항목들은 **오프라인 환경, 로컬 VLM 구조 분석, 로컬 오픈소스 임베딩 모델(BGE)**을 사용하고자 할 때만 선택적으로 설치·구성하는 항목입니다.

---

### 1. (선택) 사전 구축 벡터 인덱스 다운로드 (Prebuilt Index)

기본 워크플로 중 `Pre-built Vector Index Loader` 노드를 사용할 경우, 사전 임베딩된 파케이 파일을 구글 드라이브에서 받아 `data/source_files/`에 배치합니다.

| 파일명 | 설명 | 필수 여부 |
|---|---|:---:|
| `SPG_Company_KeyStats_v3_prebuilt.parquet` | Key Stats 시트 사전 임베딩 인덱스 (`text-embedding-3-large`) | (선택 - Optional) |

```text
data/source_files/
└── SPG_Company_KeyStats_v3_prebuilt.parquet   ← (선택) 구글 드라이브에서 다운로드 후 배치
```

> [!TIP]
> **직접 인덱스를 빌드하여 Export하려면**:
> `cell_text_embedder` → `vector_index_writer` 실행 후 아래 도구로 export 가능합니다.
> ```bash
> python -m backend.tools.export_prebuilt_index --index-id <INDEX_ID> --output data/source_files/SPG_Company_KeyStats_v3_prebuilt.json
> ```

---

### 2. (선택) Excel 원본 데이터 파일 배치

Excel 파일을 직접 파싱/구조분석/임베딩하는 수집 파이프라인을 실행할 때 원본 파일을 배치합니다.

| 파일명 | 대상 기업 | 위치 |
|---|---|---|
| `SPG_Company_KeyStats_v3.xlsm` | IBM 등 다중 기업 Key Stats | `data/source_files/` |

```text
data/source_files/
└── SPG_Company_KeyStats_v3.xlsm   ← (선택) 직접 파싱 시 배치
```

---

### 3. (선택) 로컬 VLM 구조 분석 모델 설치 (Ollama Qwen-VL)

Excel 표 구조 분석 노드 중 `Local VLM Structure Detector` 노드를 사용할 때 로컬 VLM을 구동합니다.

```bash
# 1) Ollama 설치 (https://ollama.com)
# 2) Qwen 2.5/3 VL 모델 풀
ollama pull qwen3-vl:4b-instruct
```

---

### 4. (선택) 로컬 BGE 임베딩 모델 설치 (Hugging Face BAAI/bge-large-en-v1.5)

OpenAI API 대신 **로컬 CPU/GPU 환경에서 오픈소스 임베딩**을 수행할 때 설치합니다.

```bash
python -c "from transformers import AutoModel, AutoTokenizer; AutoTokenizer.from_pretrained('BAAI/bge-large-en-v1.5'); AutoModel.from_pretrained('BAAI/bge-large-en-v1.5')"
```

`Embedder` 또는 `Cell Text Embedder` 노드 설정에서 모델을 `BAAI/bge-large-en-v1.5`로 선택하여 로컬 임베딩으로 전환할 수 있습니다.

---

### 5. (선택) Kubernetes 로컬 모델 지원 워커 빌드

Kubernetes 배치 워커 컨테이너에서 PyTorch 및 Hugging Face BGE 로컬 모델을 구동하려면 `--target local-models` 타겟으로 빌드하여 k3d 클러스터에 import합니다:

```bash
# 로컬 모델 지원 도커 이미지 빌드
DOCKER_BUILDKIT=1 docker build \
  --target local-models \
  -f jobs/workflow_worker/Dockerfile \
  -t bist-workflow-worker:local-models .

# k3d 클러스터에 이미지 임포트
k3d image import bist-workflow-worker:local-models --cluster bist-local
```

---

## Kubernetes 배치 인프라 및 운영 관리

로컬 배치 실행 인프라를 손쉽게 제어할 수 있는 관리 명령을 제공합니다.

### 주요 관리 명령어

```bash
# 클러스터 및 KEDA 상태 종합 확인
./deploy/kubernetes/local.sh status

# 클러스터 및 pgvector 재시작
./deploy/kubernetes/local.sh restart

# k3d 노드 일시 중지 (DB 볼륨 및 리소스 보존)
./deploy/kubernetes/local.sh down

# k3d 노드 다시 시작
./deploy/kubernetes/local.sh up

# 클러스터 및 배치 Job 이력 삭제 (pgvector 데이터 볼륨은 영속 보존)
./deploy/kubernetes/local.sh destroy

# 전체 초기화 후 재구축
./deploy/kubernetes/local.sh all

# KEDA ScaledJob 실시간 모니터링
kubectl get scaledjobs,jobs,pods -n bist-batch -w
```

최초 설치를 마친 뒤에는 Docker Desktop을 시작하고 아래 상태를 먼저 확인한다.

```bash
./deploy/kubernetes/local.sh restart
./deploy/kubernetes/local.sh status
```

클러스터나 워커 이미지를 아직 만들지 않았다면 idempotent 설치 명령을 다시 실행한다.

```bash
./deploy/kubernetes/local.sh all
```

그 다음 [새 환경 설치의 서버 실행](#6-서버-실행)처럼 FastAPI와 프론트엔드를 각각
실행한다. Excel 적재 API는 run만 PostgreSQL에 저장하며 실제 연산은 Job Pod가 맡는다.

```bash
source .venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 8765 --reload
```

### 정적 프론트엔드 빌드

```bash
cd frontend
npm run build

cd ..
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

빌드된 SPA는 FastAPI의 `http://127.0.0.1:8765`에서 함께 제공된다.

### 테스트

```bash
source .venv/bin/activate
python -m pytest -q

cd frontend
npm run build
npm test -- --run
```

세부 실행 구조와 컴포넌트의 책임 범위는
[배치 워커 실행 아키텍처](./docs/batch_execution_architecture.md)를 참고한다.

---

## 운영·문제 해결 명령

### 상태와 로그

```bash
./deploy/kubernetes/local.sh status
docker compose -f docker-compose.db.yml ps

# 최근 Kubernetes 워커 로그
./deploy/kubernetes/local.sh logs

# pgvector 로그
docker compose -f docker-compose.db.yml logs --tail=200 pgvector
```

### 변경 종류별 재배포

| 변경 | 명령 |
|---|---|
| API/프론트 코드만 변경 | 개발 서버 재시작 또는 hot reload |
| Job이 import하는 `backend/`·`jobs/` 코드 변경 | `./deploy/kubernetes/local.sh build` |
| `.env`·Secret·ScaledJob 설정 변경 | `./deploy/kubernetes/local.sh deploy` |
| requirements 또는 전체 배포 요소 변경 | `./deploy/kubernetes/local.sh all` |

Job 이미지 Dockerfile은 requirements를 소스보다 먼저 복사하고 BuildKit cache mount를
사용한다. requirements가 그대로면 설치 레이어를 재사용하고, requirements가 바뀌어도
다운로드한 wheel 캐시를 재사용한다.

### 자주 발생하는 문제

- **요청은 queued인데 Job이 생기지 않음**: `kubectl describe scaledjob
  excel-ingestion -n bist-batch`의 Conditions/Events와 KEDA operator 로그를 확인한다.
- **Job의 DB 연결 실패**: `docker compose ... ps`와 pgvector 로그를 확인한 뒤
  `./deploy/kubernetes/local.sh deploy`로 Kubernetes Secret을 갱신한다.
- **Excel 파일을 찾지 못함**: 파일이 저장소의 `data/source_files/` 아래 있는지 확인한다.
  저장소 경로를 옮겼다면 기존 클러스터를 `destroy`하고 다시 만들어 hostPath를 갱신한다.
- **Pod가 Pending**: `kubectl describe pod -n bist-batch <POD>`로 CPU/메모리 부족을
  확인한다. Docker Desktop 메모리를 늘린 뒤 클러스터를 재시작한다.
- **5432, 5173, 8765 포트 충돌**: 해당 프로세스를 종료하거나 `.env`와 실행
  명령에서 사용 포트를 함께 변경한다. `PGVECTOR_PORT`를 바꾸면 `PGVECTOR_URL`도 같은
  포트로 맞춘다.

### 종료와 초기화

```bash
# k3d 노드 중지. 클러스터 리소스는 보존
./deploy/kubernetes/local.sh down

# 클러스터와 Job 이력까지 삭제. 제품 pgvector volume은 보존
./deploy/kubernetes/local.sh destroy

# pgvector 컨테이너 중지. DB volume은 유지
docker compose -f docker-compose.db.yml down
```

`down`은 클러스터를 정지하고 `destroy`는 k3d 리소스를 삭제한다. 둘 다 제품
`pgvector_data` volume과 `data/` 디렉터리는 삭제하지 않는다. DB까지 초기화할 때만
명시적으로 `docker compose -f docker-compose.db.yml down -v`를 사용한다.

---

## 프로젝트 구조

저장소 루트가 곧 애플리케이션 루트입니다. 별도의 중간 프로젝트 디렉터리를 두지 않습니다.

### 백엔드

| 파일 / 디렉터리 | 역할 |
|---|---|
| `app.py` | 애플리케이션 생성, 정적 프론트엔드 제공 |
| `backend/core/settings.py` | 디렉터리 경로·환경 설정 상수 정의 |
| `backend/api/` | 공유 서비스 조립과 Modules·Workflows·Artifact HTTP 라우터 |
| `backend/data_sources/` | HTTP와 무관한 Excel 적재 job 생성·상태 조회 규칙 |
| `backend/runtime/` | 모듈 등록소와 취소 가능한 격리 프로세스 실행기 |
| `backend/runtime/services.py` | API와 외부 job이 공유하는 런타임 서비스 조립 |
| `backend/modules/` | 프론트 노드와 1:1 대응하는 Python 실행 모듈 |
| `backend/modules/data_lineage.py` | 질문·문서 계보를 보존하는 공통 DTO |
| `backend/modules/docs/` | 등록된 25개 모듈의 자동 생성 사용 가이드 |
| `backend/storage/` | 답변 캐시·임베딩 아티팩트·벡터 인덱스 영속화 |
| `backend/embeddings/` | BGE·OpenAI 임베딩 인코더와 provider factory |
| `backend/llm/` | OpenAI 호환 Chat Completions 클라이언트와 비용 계산 |
| `backend/vision/` | Ollama·OpenAI Responses 비전 클라이언트 |
| `backend/retrieval/` | 캐시 검색 등 재사용 가능한 검색 알고리즘 |
| `backend/documentation/` | Pydantic 계약 기반 모듈별 Markdown 생성기 |
| `backend/tools/run_module.py` | 프론트 없이 단일 모듈을 실행하는 CLI |
| `backend/tools/generate_module_docs.py` | 모듈 가이드 재생성 CLI |
| `backend/spreadsheets/` | Excel 탐색, 원본 스타일 PNG 렌더링, 셀 가시성·의미 분석, BFS 표 분리, 테이블 기하 계산, 계층 헤더 구성, Docling 좌표 변환 |
| `backend/workflows/models.py` | 캔버스·연결·run·노드 상태 JSON 스키마 |
| `backend/workflows/store.py` | 워크플로·run·결과 캐시 원자적 저장 |
| `backend/workflows/executor.py` | 포트 검증, 위상 배치, 순환 검출, 실행 재개 |
| `backend/workflows/history.py` | run 노드 출력 이력 압축 |
| `backend/workflows/dispatcher.py` | 대화형 Playground run의 백그라운드 실행 수명주기 |
| `backend/orchestration/` | DAG task 계획과 PostgreSQL/Kubernetes queue dispatcher |
| `jobs/workflow_worker/` | run 하나를 claim·실행하는 one-shot Job 이미지 |
| `deploy/kubernetes/` | k3d·KEDA·Metrics Server·ScaledJob 로컬 배포 |

`backend/` 바로 아래에는 패키지 표시용 `__init__.py`만 둡니다. 새 코드는 역할에 맞는 하위 패키지에 배치하고, 외부 API·워크플로 계층에서 모듈 구현 세부사항을 직접 소유하지 않습니다. 세부 의존 방향과 모듈 추가 규칙은 [Backend module architecture](./docs/backend_module_architecture.md)를 참고하세요.

### 프론트엔드

| 파일 / 디렉터리 | 역할 |
|---|---|
| `frontend/src/App.tsx` | 현재 URL을 공통 셸과 페이지에 연결하는 애플리케이션 진입점 |
| `frontend/src/app/routes.ts` | 메뉴와 페이지 컴포넌트의 단일 라우트 레지스트리 |
| `frontend/src/app/router.tsx` | History API 기반 내부 탐색과 링크 |
| `frontend/src/app/AppShell.tsx` | 홈·기능 페이지가 공유하는 사이드바와 상단 바 |
| `frontend/src/pages/` | 홈과 팀원이 독립적으로 구현할 서비스 페이지 경계 |
| `frontend/src/features/playground/` | 기존 RAG 캔버스의 컴포넌트·상태·API·스타일 전체 |
| `frontend/src/shared/` | 여러 서비스 페이지가 함께 사용하는 UI |
| `frontend/src/styles/global.css` | 디자인 토큰과 전역 reset |
| `frontend/src/styles/app.css` | 서비스 셸·홈·빈 페이지의 반응형 스타일 |

서비스 홈은 `/`, 파이프라인 실험 기능은 `/playground`입니다. 향후 메뉴 페이지를 추가하는 방법과 디렉터리 의존 규칙은 [Frontend architecture](./docs/frontend_architecture.md)에 정리되어 있습니다.

### 데이터 디렉터리 (Git 제외)

| 경로 | 내용 |
|---|---|
| `data/source_files/` | 입력 Excel 파일 및 사전 구축 인덱스 |
| `data/runs/` | 실행별 입력·출력·상태 |
| `data/cache/` | 모듈 타입·버전·입력 기반 결과 캐시 |
| `data/vector_db/` | 문서 벡터 인덱스·메타데이터 |
| `data/artifacts/embeddings/` | 콘텐츠 주소형 float32 임베딩 파일 |
| `data/artifacts/spreadsheets/` | 시트별 렌더링·타입 오버레이·Docling 주석 이미지 |
| `data/workflows/workflow.json` | 사용자 편집 워크플로 (로컬 전용) |

`data/workflows/default.json`, `main_dag_pipeline.json`, `indexing_prebuilt.json`, `system_architecture.json`은 예제·기본 워크플로로 저장소에 포함됩니다. 사용자가 편집하는 `workflow.json`과 실행 데이터는 로컬에만 저장됩니다.

---

## 모듈 실행 계약

프론트엔드는 `GET /api/modules` 에서 모듈 이름·설명·입출력 계약을 읽습니다. 각 모듈은 독립 실행도 가능합니다.

```
POST /api/modules/{module_type}/execute
```

실행 요청은 연결 데이터와 노드 설정을 명시적으로 분리합니다.

```json
{
  "input": {"any_json": {"source": 7}},
  "config": {"mappings": {"source": "target"}}
}
```

응답은 해당 모듈의 Output DTO JSON입니다. 프론트 없이 같은 계약을 실행하려면 다음 CLI를 사용할 수 있습니다.

```bash
python -m backend.tools.run_module json_transformer --request request.json
python -m backend.tools.run_module json_transformer --contract
```

DTO 경계와 모듈 추가 규칙은 [Backend module architecture](docs/backend_module_architecture.md)에 정리되어 있습니다. 프로젝트 문서의 전체 목록은 [docs/README.md](docs/README.md)에서 확인합니다.

서버 실행 후 자동 개발 문서는 다음 주소에서 확인합니다.

- Swagger UI: `http://localhost:8765/docs`
- ReDoc: `http://localhost:8765/redoc`
- OpenAPI JSON: `http://localhost:8765/openapi.json`
- 모듈별 Markdown: [`backend/modules/docs/`](backend/modules/docs/README.md)

모듈 DTO 또는 포트를 수정한 뒤 Markdown 문서를 다시 생성합니다.

```bash
python -m backend.tools.generate_module_docs
```

기본 파이프라인도 동일한 모듈 레지스트리를 순서대로 실행하므로, 화면용 데이터와 독립 실행 결과가 서로 다른 코드 경로를 사용하지 않습니다.

| 프론트 노드 | 백엔드 파일 | 주요 입력 | 주요 출력 |
|---|---|---|---|
| Query Input | `backend/modules/query_input.py` | `query` | `cached_answer` 또는 `query_context` |
| Decomposer | `backend/modules/decomposer.py` | `query_context` | `query_context`, `subqueries` |
| Embedder | `backend/modules/embedder.py` | `query_context`, `subqueries` | `query_context`, `items{subquery: embedding}` |
| BM25 Retriever | `backend/modules/bm25_retriever.py` | `query_input`, `document_input` | `query_context`, `document_context`, BM25 후보 |
| Cell Text Embedder | `backend/modules/cell_text_embedder.py` | Serializer 출력 | 셀 메타데이터, float32 아티팩트 참조 |
| Vector Index Writer | `backend/modules/vector_index_writer.py` | Cell Text Embedder 출력 | `index_id`, 파일·해시·모델·차원·문서 개수 |
| Dense Retriever | `backend/modules/dense_retriever.py` | `query_input`, `index_input` | `query_context`, `document_context`, Dense 후보 |
| RRF Fusion | `backend/modules/rrf_fusion.py` | `bm25_result`, `dense_result` | 계보가 검증된 셀 단위 Top-K |
| Context Expander | `backend/modules/context_expander.py` | `retrieval_json`, `document_input` | 두 계보와 인접 ±N행 실제 값을 담은 `context_json` |
| Reader | `backend/modules/reader.py` | `context_json` | 두 계보가 포함된 근거 기반 `answer_json` |
| Answer Cache Writer | `backend/modules/answer_cache_writer.py` | `answer_json` | Query Context 기준 캐시 저장 후 동일 답변 |
| JSON Transformer | `backend/modules/json_transformer.py` | `any_json` | `transformed_json` |
| JSON Inspector | `backend/modules/json_inspector.py` | 원본 JSON | 원본 JSON (passthrough) |
| Processed Excel Selector | `backend/modules/processed_file_selector.py` | `file_name` (Input) | `file_name`, `workbook_hash`, `sheet_names` |
| BFS + LLM Structure Detector | `backend/modules/bfs_llm_structure_detector.py` | workbook DTO | 영역 좌표, `header_tree` |
| Local VLM Structure Detector | `backend/modules/local_vlm_structure_detector.py` | workbook DTO | spreadsheet structure DTO |
| Luna Full-Sheet Structure Detector | `backend/modules/luna_vlm_structure_detector.py` | workbook DTO | spreadsheet structure DTO |
| Docling Table Detector | `backend/modules/docling_table_detector.py` | workbook DTO | 평탄 `tables[]` |
| OpenPyXL Region Classifier | `backend/modules/openpyxl_region_detector.py` | 평탄 `tables[]` | 영역·`header_tree`가 있는 `tables[]` |
| Structured Cell Text Serializer | `backend/modules/cell_text_serializer.py` | spreadsheet structure DTO | 셀별 `header_only`, `header_with_value` |
| Exhaustive Cell Header Serializer | `backend/modules/exhaustive_cell_text_serializer.py` | workbook DTO | 헤더 후보 조합 문서 |
| Pre-built Index Loader | `backend/modules/prebuilt_index_loader.py` | `file_name` (Input) | `document_output`, `index_output` |
| DataFrame Source | `backend/modules/dataframe_source.py` | `file_name` (Input) | 시트 스키마·샘플 |
| Image Tile Source | `backend/modules/image_tile_source.py` | `file_name`, `sheet_name` | 이미지 타일 메타데이터 |
| QA Example Loader | `backend/modules/qa_example_loader.py` | `file_name` | QA 예시 목록 |

### 질문·문서 계보

검색과 답변 DTO는 데이터가 무엇을 나타내는지 명시하는 공통 컨텍스트를 끝까지 전달합니다.

- `QueryContextDTO`: `question_id`, `question_text`
- `DocumentContextDTO`: `file_name`, `workbook_hash`

```mermaid
flowchart LR
    Q["Query Input"] -->|query_context| D["Decomposer"]
    D --> E["Embedder"]
    D --> B["BM25"]
    E --> V["Dense"]
    DOC["Document DTO"] --> B
    IDX["Index DTO"] --> V
    B --> R["RRF"]
    V --> R
    R --> C["Context Expander"]
    C --> A["Reader"]
    A --> W["Answer Cache Writer"]
```

RRF는 BM25와 Dense가 같은 질문과 문서를 나타내는지 검사합니다. Context Expander도 검색 결과와 문서 입력의 `document_context`를 대조합니다. Reader와 Cache Writer는 직전 DTO가 원 질문을 포함하므로 Query Input과 직접 연결하지 않습니다.

### 기본 질의 DAG

기본 워크플로는 사전 구축 인덱스에서 문서와 벡터 인덱스를 함께 로드합니다.

```mermaid
flowchart LR
    Q["Query Input"] --> D["Decomposer"]
    D --> E["Embedder"]
    D --> B["BM25"]
    P["Pre-built Index Loader"] --> B
    P --> V["Dense"]
    E --> V
    B --> R["RRF"]
    V --> R
    R --> C["Context Expander"]
    P --> C
    C --> A["Reader"]
```

---

## 스프레드시트 파이프라인

### 공통 규칙

- `data/source_files/` 내부 파일만 선택할 수 있습니다.
- 숨김 시트, 숨김 행·열, 높이·너비 0인 행·열, 그룹으로 접힌 열은 전체 애플리케이션에서 존재하지 않는 데이터로 취급합니다. 어느 모듈도 해당 셀 값을 읽거나 중간 DTO·캐시에 포함하지 않습니다.

### 인덱싱 DAG 예시

```
Processed Excel Selector
  → Luna Full-Sheet Structure Detector
  → Structured Cell Text Serializer
  → Cell Text Embedder
  → Vector Index Writer
```

이 구성은 `data/workflows/indexing_prebuilt.json`에 저장되어 있습니다. 구조 Detector는 같은 Spreadsheet Structure DTO를 출력하므로 Luna 대신 Local VLM, BFS + LLM, Docling/OpenPyXL 경로로 교체할 수 있습니다.

Local VLM 모듈은 원본 스타일 렌더링 위에 값 셀을 `text·number·date·boolean·error` 타입별로 반투명 채색하고, 수식 셀에는 별도 테두리를 표시합니다. 이미지와 압축 JSON을 로컬 Ollama(`qwen3-vl:4b-instruct`)에 전달하며 외부 API 비용이 없습니다. 응답은 strict JSON Schema로 제한하고, 모델이 선언한 헤더·데이터 경계를 전체 데이터를 덮는 공통 직사각형 DTO로 정규화합니다.

### 구조 추출 노드 비교

다섯 가지 구조 추출 노드(Docling, OpenPyXL, BFS + LLM, Local VLM, Luna Full-Sheet)는 동일한 결과 검사 팝업을 제공하며, 모두 `spreadsheet_structure.py`의 공통 DTO를 출력하므로 Serializer 앞에서 자유롭게 교체할 수 있습니다.

| 노드 | 방법 | 외부 API |
|---|---|---|
| BFS + LLM | 4방향 연결요소 → 표 상단 10행을 LLM에 배치 전달 | ✅ (Chat Completions) |
| Local VLM | 원본+타입 오버레이 이미지 → Ollama | ❌ (로컬) |
| Luna Full-Sheet | 전체 시트 이미지 1장 → OpenAI Responses API | ✅ (Responses API) |
| Docling | PDF 레이아웃 분석으로 bbox 추출 | ❌ |
| OpenPyXL | Docling bbox + 서식·밀도 분석 | ❌ |

Luna Full-Sheet는 타일 분할 없이 시트 전체를 단일 이미지로 처리합니다. 데이터 행렬 위치의 `NA`, `N/A`, `NM`, 대시 같은 결측·상태 표시는 텍스트 타입이어도 데이터로 유지하는 규칙이 Luna, Local VLM, BFS + LLM에 공통 적용됩니다.

### 구조 추론 없는 대체 경로

```
Processed Excel Selector
  → Exhaustive Cell Header Serializer
  → BGE Cell Text Embedder
  → Vector Index Writer
```

Exhaustive Serializer는 모든 값 셀의 왼쪽·위쪽 헤더 후보 데카르트 곱을 생성합니다. 조합 수가 안전 한도를 초과하면 자르지 않고 실행을 실패시키므로, 필요 시 설정에서 한도를 명시적으로 조정해야 합니다.

### 임베딩·인덱스 저장

숫자 벡터 본문은 워크플로 실행 JSON에 포함하지 않습니다.

- **Cell Text Embedder** → `data/artifacts/embeddings/` (콘텐츠 주소형 float32)
- **Vector Index Writer** → `data/vector_db/` (정규화 float32 행렬 + 셀 메타데이터)
- **Dense Retriever** → `index_id` 만 받아 exact cosine 검색 수행

인덱스 ID에 포맷 버전·임베딩 아티팩트 ID가 반영되므로 workbook·문서 텍스트·모델이 바뀌면 새 인덱스가 생성됩니다. API 프로세스에 FAISS/OpenMP를 로드하지 않아 Torch 계열 모듈과의 런타임 충돌을 피합니다.

### 검색 전략

각 서브쿼리마다 BM25·Dense 순위를 생성한 뒤 같은 서브쿼리의 rank만 RRF로 합산하고, dual-view 표현을 Cell ID로 축약해 Top 100을 선택합니다. 비율 의도가 없는 질문의 margin·ratio 행에는 기본 `ratio_penalty=0.4`가 적용됩니다. Context Expander는 같은 시트의 인접 ±3행·전체 열을 복원하고, Reader는 `context_json` 내부의 원문 질문과 근거 블록으로 답변과 Cell ID 인용을 생성합니다.

---

## 워크플로 저장 형식

기본 캔버스 템플릿은 `data/workflows/default.json`에 저장됩니다. 애플리케이션은 `data/workflows/workflow.json`을 우선 사용하고, 파일이 없을 때만 `default.json`으로 폴백합니다. 사용자가 캔버스를 저장하면 `workflow.json`에만 기록되며 `default.json`은 수정되지 않습니다.

JSON에 포함되는 편집 정보:

- `schema_version`, 워크플로 ID·이름
- 노드 ID, Python 모듈 타입, 위치
- `config` — 모델·프롬프트·threshold·top-k처럼 같은 입력을 처리하는 정책
- `values` — 질문·파일명·시트명처럼 해당 실행의 데이터 또는 데이터 정체성
- `ui` — Inspector처럼 사용자가 조절한 노드 너비 등 캔버스 표현 정보
- 연결 ID, 시작·도착 노드, 선택적 출력·입력 포트
- 캔버스 이동·확대/축소 값

여러 출력·입력 포트를 갖는 모듈은 연결의 `source_output`, `target_input`을 명시합니다. 포트가 각각 하나뿐인 경우에만 생략 시 자동 추론합니다.

노드 위치, 연결, 모듈 설정, 뷰포트는 **700ms 디바운스**로 자동 저장됩니다.

---

## 배치 DAG 실행과 상태 전달

실행을 생성하면 워크플로 정의 전체가 run에 스냅샷으로 복사됩니다. 실행 중 캔버스를 수정해도 이미 시작된 run의 의미는 바뀌지 않습니다.

**실행 순서:**

1. 모든 연결과 포트를 검증하고 순환을 거부합니다.
2. 위상 깊이가 같은 준비된 노드를 하나의 배치로 묶습니다.
3. `values` + 런타임 입력 + 선행 노드의 명명된 출력으로 Input DTO를 만들고, 노드 `config`는 별도 Config DTO로 검증합니다.
4. 노드 실행 전후마다 `data/runs/{run_id}.json`을 원자적으로 갱신합니다.
5. 다음 배치는 파일에 저장된 선행 출력을 읽어 입력 포트로 전달합니다.
6. 서버가 중단되면 `running` 상태만 `pending`으로 되돌리고, 성공한 노드 출력은 그대로 유지해 이어서 실행합니다.

**캐시:** 결정적 모듈은 `module_type + version + {input, config}`의 SHA-256 키로 결과를 캐시합니다. 부작용 모듈(Answer Cache Writer 등)과 명시적으로 `cacheable=false`인 모듈은 캐시 대상에서 제외됩니다.

**노드 단위 재실행:** 재생 버튼은 선택한 노드 하나만 실행합니다. 하위 노드는 자동 실행되지 않으며, 전체 자동 실행은 기존 배치 단위 위상 실행을 사용합니다.

---

## API 레퍼런스

### 모듈

```
GET    /api/modules
GET    /api/modules/{module_type}
GET    /api/modules/{module_type}/docs
POST   /api/modules/{module_type}/execute
```

### 워크플로

```
GET    /api/workflows
GET    /api/workflows/{workflow_id}
PUT    /api/workflows/{workflow_id}
```

### Run

```
POST   /api/workflows/{workflow_id}/runs          # run 생성
POST   /api/workflows/{workflow_id}/execute       # run 생성 후 전체 배치 실행 (one-shot)
GET    /api/runs
GET    /api/runs?workflow_id={id}
GET    /api/runs/{run_id}
POST   /api/runs/{run_id}/execute                 # 남은 모든 배치 실행
POST   /api/runs/{run_id}/execute-next            # 준비된 다음 배치만 실행
POST   /api/runs/{run_id}/nodes/{node_id}/execute # 노드 하나만 실행
POST   /api/runs/{run_id}/resume                  # 실패 노드 재시도 후 이어서 실행
POST   /api/runs/{run_id}/cancel                  # 실행 중인 격리 프로세스 즉시 종료
DELETE /api/cache                                 # 결과 캐시·run 이력 삭제 (워크플로 보존)
```

### 스프레드시트 아티팩트

```
GET    /api/spreadsheet-artifacts/{workbook_hash}/sheets/{sheet_name}
         ?layer=rendered|typed|docling
```

## 개발 문서 관리

API 문서의 원본은 Python docstring, `ModuleDefinition`, Pydantic DTO입니다. 서버가 시작되면 FastAPI가 OpenAPI를 생성하고 Swagger UI와 ReDoc이 이를 즉시 반영합니다.

| 문서 | 주소/경로 | 용도 |
|---|---|---|
| ReDoc | `/redoc` | 전체 API와 DTO를 읽고 탐색 |
| Swagger UI | `/docs` | 요청 JSON을 입력해 API 직접 실행 |
| OpenAPI | `/openapi.json` | 클라이언트·문서 도구용 기계 판독 계약 |
| 모듈 Markdown | `backend/modules/docs/` | 팀원이 파일 단위로 보는 모듈 사용법 |
| 아키텍처 | `docs/backend_module_architecture.md` | DTO 분류, 계보, 모듈 추가 규칙 |

모듈 계약을 변경하면 자동 생성 Markdown을 갱신하고 테스트합니다.

```bash
python -m backend.tools.generate_module_docs
python -m unittest discover -s tests
cd frontend && npm run build
```

`backend/modules/docs/*.md`는 직접 편집하지 않습니다. 테스트가 생성 결과와 체크인된 파일의 일치 여부를 검증합니다.
