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
# 전체 테스트 실행 (단위 테스트 + BI + 파이프라인 통합 테스트)
uv run pytest

# 개별 모듈 단위 테스트만 실행
uv run pytest tests/modules -v

# RAG 파이프라인 E2E 통합 테스트만 실행
uv run pytest tests/test_modules_pipeline.py -v
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
├── backend/                  # FastAPI 백엔드, BI 엔진, DB 및 프로바이더
│   ├── api/                  # REST 엔드포인트 및 라우터
│   ├── bi/                   # BI 메트릭 분석, 질의 워커, 스냅샷 스토어
│   ├── engine/               # 워크플로 DAG 실행기 및 모듈 레지스트리
│   └── storage/              # PostgreSQL pgvector 스토어 및 아티팩트
├── frontend/                 # React, Vite, TailwindCSS, XYFlow 시각화 UI
├── modules/                  # 19개 표준 RAG 파이프라인 모듈 (Single Source of Truth)
│   ├── common/               # BaseModule, BaseLLMModule, BaseEmbedderModule
│   ├── embedding/            # Query & Cell Text Embedders
│   ├── query/                # QueryInput, Decomposer, Router, Matcher
│   ├── reader/               # Agentic Reader & Tools
│   ├── retrieval/            # Dense/Sparse Retriever, RRF Fusion, Expander
│   └── storage/              # File Selector, Metadata Persistence, PG Loader/Writer
├── tests/                    # 테스트 스위트
│   ├── modules/              # 19개 모듈별 독립 단위 테스트 (test_*.py)
│   ├── test_base_module.py   # BaseModule/BaseLLMModule 공통 기능 검증
│   └── test_modules_pipeline.py # RAG 파이프라인 E2E 통합 테스트
└── data/                     # 워크플로 템플릿 및 데이터 저장소
```
