# BIST Mini Final - RAG Pipeline & BI Visualizer

복잡한 재무제표 엑셀 스프레드시트 구조 분석, 멀티모달 VLM 테이블 감지, pgvector 기반 하이브리드 검색(Dense + Sparse RRF), 에이전틱 리더 및 BI 메트릭 분석 대시보드를 제공하는 엔드투엔드 RAG 파이프라인 시스템입니다.

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 1. 환경 설정 (Prerequisites)

- **Python**: `3.11+` (패키지 관리자: [`uv`](https://github.com/astral-sh/uv) 권장)
- **Node.js**: `v18+` (NPM `v9+`)
- **PostgreSQL**: `pgvector` 확장이 활성화된 DB (`localhost:5432/rag_flow`)

```bash
# 환경 변수 설정
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 및 PGVECTOR_URL을 입력합니다.
```

---

### 2. 백엔드 실행 (Backend)

```bash
# 의존성 동기화 (uv 사용)
uv sync

# FastAPI 백엔드 서버 실행 (포트: 8765)
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
```

- **Swagger API Docs**: [http://localhost:8765/docs](http://localhost:8765/docs)
- **ReDoc**: [http://localhost:8765/redoc](http://localhost:8765/redoc)

---

### 3. 프론트엔드 실행 (Frontend)

```bash
cd frontend

# 의존성 설치
npm install

# Vite 개발 서버 실행 (포트: 5173)
npm run dev
```

- **웹 대시보드 UI**: [http://localhost:5173](http://localhost:5173)

---

## 🧪 테스트 실행 (Testing)

### 백엔드 테스트 (Pytest)
```bash
# 전체 테스트 실행 (모듈 단위/통합 테스트 + BI 스위트)
uv run pytest

# 모듈 단위 및 파이프라인 통합 테스트 실행
uv run pytest tests/modules -v

# 특정 모듈 단위 테스트 실행 (예: Decomposer)
uv run pytest tests/modules/test_decomposer.py -v
```

### 프론트엔드 테스트 (Vitest)
```bash
cd frontend
npm test
```

---

## 📂 프로젝트 구조 (Architecture)

```
bist-mini-final/
├── modules/                  # 19개 표준 RAG 단위 모듈 (Single Source of Truth)
│   ├── common/               # BaseModule, BaseLLMModule, BaseEmbedderModule
│   ├── embedding/            # Query & Cell Text Embedders
│   ├── query/                # QueryInput, Decomposer, Router, Matcher
│   ├── reader/               # Agentic Reader & Tools
│   ├── retrieval/            # Dense/Sparse Retriever, RRF Fusion, Expander
│   └── storage/              # File Selector, Metadata Persistence, PG Loader/Writer
├── jobs/                     # 선언적 파이프라인 Job 조합 레시피 (Pure Compositions)
│   ├── excel_ingestion.py    # 엑셀 구조화 및 pgvector 인덱싱 Job 정의
│   ├── bi_materialization.py # BI 재무제표 메트릭 분석 Job 정의
│   └── rag_pipeline.py       # 하이브리드 RAG 질의응답 파이프라인 Job 정의
├── backend/                  # FastAPI 백엔드 & 공통 런타임 엔진
│   ├── api/                  # REST API 라우터 (Producer)
│   ├── bi/                   # BI 메트릭 분석 및 대시보드 스냅샷 스토어
│   ├── engine/               # PipelineRunner (인메모리 모듈 실행기)
│   │   └── worker/           # 쿠버네티스 워커 런타임 (Consumer: DB Lease & Heartbeat)
│   └── storage/              # PostgreSQL pgvector 스토어 및 아티팩트
├── frontend/                 # React, Vite, TailwindCSS, XYFlow 시각화 UI
├── deploy/                   # 배포 및 인프라 (Docker, KEDA ScaledJob, Kubernetes)
│   ├── docker/               # Dockerfile.worker
│   └── kubernetes/           # KEDA ScaledJob, Deployment, Ingress 매니페스트
└── tests/                    # 테스트 스위트
    └── modules/              # 모듈/파이프라인/워커/Job 단위 테스트
```
