# BIST Mini Final — RAG Pipeline & BI Visualizer

재무 스프레드시트 구조 분석, Luna VLM 테이블 감지, PostgreSQL/pgvector 하이브리드 검색(Dense + FTS + RRF), 근거 기반 응답, BI 스냅샷과 RAG 벤치마크를 제공하는 Kubernetes-first 시스템입니다.

제품 기능과 완료 조건의 기준은 [제품 및 기능 명세](docs/specs/README.md)입니다.

## 실행 구조

- `modules/`는 19개 계산 단위와 Pydantic 입출력 계약의 단일 소스입니다.
- `jobs/`는 module port를 연결하는 canonical DAG와 worker entrypoint의 단일 소스입니다.
- FastAPI는 계약 검증, PostgreSQL 큐 제출, compact 조회와 SSE 관찰만 수행합니다.
- 실제 계산은 KEDA가 확장하는 Kubernetes Job에서만 수행합니다.
- `workflow-core`, `bi-materialization`, `bi-question`, `benchmark` 네 큐가 서로 독립적으로 확장됩니다.
- run, lease, BI, benchmark 상태와 결과는 PostgreSQL에 영속화됩니다.
- LLM/VLM은 하나의 OpenAI Responses API client와 keep-alive connection pool을 공유하며 structured output과 tool continuation은 공식 Responses 계약을 사용합니다.
- canonical workflow는 `rag_query`, `excel_ingestion` 두 개이며 UI에서는 읽기 전용으로 제공됩니다.

## 빠른 시작

필수 도구는 Python 3.11+, `uv`, Node.js 20+, Docker, k3d, kubectl, Helm입니다.

```bash
cp .env.example .env
# .env에 OPENAI_API_KEY와 PGVECTOR_URL을 설정

uv sync --frozen
cd frontend && npm ci && cd ..

# PostgreSQL 스키마, k3d, KEDA, worker image와 4개 ScaledJob 준비
./deploy/kubernetes/local.sh all
```

API와 frontend 개발 서버는 별도 터미널에서 실행합니다.

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
```

```bash
cd frontend
npm run dev
```

- UI: [http://localhost:5173](http://localhost:5173)
- OpenAPI: [http://localhost:8765/docs](http://localhost:8765/docs)
- Kubernetes 상태: `./deploy/kubernetes/local.sh status`

API 서버만 실행하면 계약 조회와 화면 개발은 가능하지만, PostgreSQL/KEDA worker가 없을 때 실행 제출은 명시적으로 `503`을 반환하며 로컬 계산으로 폴백하지 않습니다.

## 검증

```bash
uv run ruff check modules backend jobs tests
uv run pyright
uv run pytest -q

cd frontend
npm run test
npm run build
```

Kubernetes manifest는 다음 명령으로 렌더링할 수 있습니다.

```bash
uv run python deploy/kubernetes/scripts/render.py \
  --max-replicas 4 \
  --connection-hash aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

요구사항별 자동·통합·운영 검증은 [검증 매트릭스](docs/specs/VERIFICATION_MATRIX.md)를 따릅니다.

## 프로젝트 구조

```text
bist-mini-final/
├── modules/                       # 계산 모듈과 Pydantic 계약
├── jobs/                          # canonical DAG/worker JobDefinition
│   ├── excel_ingestion.py
│   ├── rag_pipeline.py
│   ├── bi_materialization.py      # materialization + question worker
│   └── benchmark.py
├── backend/
│   ├── api/                       # 제출·조회·SSE control plane
│   ├── engine/
│   │   ├── workflows/             # DAG validation, run state, executor
│   │   ├── orchestration/         # PostgreSQL/Kubernetes dispatcher
│   │   └── worker/                # workflow-core consumer
│   ├── features/
│   │   ├── bi/                    # BI queues, workers, snapshots
│   │   └── benchmark/             # benchmark queue, worker, results
│   └── storage/                   # PostgreSQL, pgvector, shared artifacts
├── frontend/                      # React/Vite/XYFlow UI
├── deploy/                        # Docker, k3d, KEDA ScaledJobs
├── docs/specs/                    # 제품·기능·API·Job·검증 명세
└── tests/modules/                 # module/job/queue/API contract tests
```
