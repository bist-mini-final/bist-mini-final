# RAG Flow Workbench

재무 질문 처리 모듈을 캔버스에서 조합하고, 사용자가 만든 DAG를 배치 단위로 실행하는 FastAPI + React 애플리케이션입니다.

---

## 목차

1. [환경 설정](#환경-설정)
2. [개발 서버 실행](#개발-서버-실행)
3. [프로젝트 구조](#프로젝트-구조)
4. [모듈 실행 계약](#모듈-실행-계약)
5. [스프레드시트 파이프라인](#스프레드시트-파이프라인)
6. [워크플로 저장 형식](#워크플로-저장-형식)
7. [배치 DAG 실행과 상태 전달](#배치-dag-실행과-상태-전달)
8. [API 레퍼런스](#api-레퍼런스)
9. [개발 문서 관리](#개발-문서-관리)

---

## 환경 설정

> [!NOTE]
> `data/source_files/`, `data/runs/`, `data/cache/`, `data/vector_db/`, `data/artifacts/` 디렉터리는 `.gitkeep`을 통해 저장소에 포함되어 있으므로 별도로 디렉터리를 생성할 필요가 없습니다. 런타임 데이터 파일만 `.gitignore`에 의해 제외됩니다.

### 1. Python 의존성 설치

Python 3.10+ 권장. macOS 기본 Python 3.9 환경도 지원하나, Docling OCR 호환을 위해 `requirements.txt`가 PyObjC 11.1을 고정합니다.

```bash
# 1) 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate  # Windows (CMD/PowerShell): .venv\Scripts\activate

# 2) 의존성 설치
pip install -r requirements.txt
```

`requirements.txt`에는 사전 구축 `.parquet` 인덱스를 읽기 위한 `pyarrow`가 포함되어 있습니다. 기존 가상환경을 사용 중이라면 의존성 변경 후 위 명령을 다시 실행하세요.

---

### 2. 환경변수 설정

팀 노션에서 `.env` 관련 설정 정보(`OPENAI_API_KEY` 등)를 확인하여 프로젝트 루트에 `.env` 파일을 생성합니다.

```bash
cp .env.example .env
```

`.env`를 열어 팀 노션에 안내된 값을 채웁니다.

| 변수 | 필수 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | Decomposer, Reader, OpenAI Embeddings (`text-embedding-3-large`) 모듈에 사용 |
| `OPENAI_BASE_URL` | ⬜ | 기본값 `https://api.openai.com/v1`. 호환 API 사용 시 변경 |
| `PGVECTOR_URL` | ⬜ | 기본값 `postgresql://postgres:postgres@localhost:5432/rag_flow`. Docker pgvector 접속 URL |
| `USE_PGVECTOR` | ⬜ | 기본값 `true`. pgvector DB 연결 및 자동 적재 활성화 여부 |

> [!IMPORTANT]
> 기본 워크플로의 임베딩 모듈(`Embedder`, `Cell Text Embedder`)은 `text-embedding-3-large` (OpenAI API)를 기본값으로 사용합니다. `OPENAI_API_KEY`가 없으면 임베딩 단계를 실행할 수 없습니다.

---

### 3. Docker pgvector 컨테이너 실행 (Vector DB)

벡터 DB 저장소로 **PostgreSQL 16 + pgvector (`vector v0.8.6`)** 컨테이너를 구동합니다. LangChain의 `langchain-postgres`를 통해 표준 포맷으로 인덱스를 적재 및 검색합니다.

```bash
# 1) Docker 컨테이너 백그라운드 구동 (docker-compose.db.yml)
docker compose -f docker-compose.db.yml up -d

# 2) 컨테이너 상태 및 헬스체크 확인
docker compose -f docker-compose.db.yml ps

# 3) (선택) DB 로그 실시간 확인
docker compose -f docker-compose.db.yml logs -f pgvector
```

- **설정 파일**: [`docker-compose.db.yml`](file:///Users/pileuszu/Repos/bist-mini-final/docker-compose.db.yml)
- **접속 주소**: `postgresql://postgres:postgres@localhost:5432/rag_flow`
- **컨테이너 중지**: `docker compose -f docker-compose.db.yml down` (데이터는 `pgvector_data` 볼륨에 영속 보존)

---

### 4. 사전 구축 벡터 인덱스 다운로드 (Prebuilt Index)

> [!IMPORTANT]
> 기본 워크플로(`Pre-built Vector Index Loader` 노드)는 사전 임베딩된 인덱스 파일을 로드합니다. 아래 파일을 구글 드라이브에서 받아 `data/source_files/`에 배치해야 파이프라인을 바로 실행할 수 있습니다.

**구글 드라이브에서 다운로드할 파일:**

| 파일명 | 설명 |
|---|---|
| `SPG_Company_KeyStats_v3_prebuilt.parquet` | Key Stats 시트 사전 임베딩 인덱스 |

```
data/source_files/
└── SPG_Company_KeyStats_v3_prebuilt.parquet   ← 구글 드라이브에서 다운로드 후 배치
```

> [!NOTE]
> prebuilt 인덱스는 `text-embedding-3-large` 모델로 생성되었습니다. 다른 모델로 만든 인덱스를 사용하려면 Dense Retriever의 쿼리 임베딩 모델도 같은 모델로 변경해야 합니다.

**인덱스를 직접 빌드하려면** (선택):

기존 Excel 파일에서 처음부터 인덱스를 생성하려면 `cell_text_embedder` → `vector_index_writer` 파이프라인을 실행한 뒤 아래 명령으로 export합니다.

```bash
python3 -m backend.tools.export_prebuilt_index --index-id <INDEX_ID> --output data/source_files/SPG_Company_KeyStats_v3_prebuilt.json
```

---

### 5. Excel 파일 배치

팀 구글 드라이브에서 분석 대상 Excel 파일을 다운로드하여 `data/source_files/` 에 복사합니다.

- **기본 워크플로 사용 파일**: `SPG_Company_KeyStats_v3.xlsm`

```
data/source_files/
└── SPG_Company_KeyStats_v3.xlsm   ← 구글 드라이브에서 다운로드 후 배치 (Excel 직접 파싱 파이프라인에만 필요)
```

> [!NOTE]
> 사전 구축 인덱스(`prebuilt.parquet`)를 사용하는 기본 워크플로에서는 Excel 원본 파일 없이도 검색·답변 파이프라인을 실행할 수 있습니다. Loader는 이전 JSON 포맷도 호환합니다.

### 6. 프론트엔드 의존성 설치

```bash
cd frontend
npm install
```

### 7. (선택) 로컬 VLM 모델 설치

Local VLM Structure Detector 노드를 사용하려면 Ollama와 모델이 필요합니다.

```bash
# Ollama 설치: https://ollama.com
ollama pull qwen3-vl:4b-instruct
```

### 8. (선택) 로컬 BGE 임베딩 모델 설치

`BAAI/bge-large-en-v1.5` 모델을 사용하려면 (OpenAI API 없이 로컬 임베딩을 원할 때) 최초 1회 모델을 다운로드해야 합니다.

> [!NOTE]
> 기본 워크플로는 `text-embedding-3-large` (OpenAI API)를 사용하므로 **BGE 설치는 선택 사항**입니다. 로컬 임베딩이 필요한 경우에만 아래 명령을 실행하세요.

```bash
python3 -c "from transformers import AutoModel, AutoTokenizer; AutoTokenizer.from_pretrained('BAAI/bge-large-en-v1.5'); AutoModel.from_pretrained('BAAI/bge-large-en-v1.5')"
```

`Embedder` 또는 `Cell Text Embedder` 노드의 모델 설정에서 `BAAI/bge-large-en-v1.5`를 선택하면 로컬 모델을 사용합니다.

---

## 개발 서버 실행

데이터베이스, 프론트엔드, 백엔드를 순서대로 실행합니다.

```bash
# 1. Vector DB (Docker pgvector 컨테이너) 백그라운드 실행
docker compose -f docker-compose.db.yml up -d

# 2. 터미널 1 — 프론트엔드 개발 서버 (Hot Reload)
cd frontend
npm run dev

# 3. 터미널 2 — 백엔드 FastAPI 서버
python3 -m uvicorn app:app --host 127.0.0.1 --port 8765
```

브라우저에서 `http://localhost:5173` 을 열면 됩니다.

### 프로덕션 빌드

```bash
cd frontend
npm run build   # TypeScript 엄격 검사 후 dist/ 생성

cd ..
python3 -m uvicorn app:app --host 127.0.0.1 --port 8765
# 빌드된 정적 파일을 http://localhost:8765 에서 제공
```

### 테스트

```bash
python3 -m unittest discover -s tests
```

---

## 프로젝트 구조

저장소 루트가 곧 애플리케이션 루트입니다. 별도의 중간 프로젝트 디렉터리를 두지 않습니다.

### 백엔드

| 파일 / 디렉터리 | 역할 |
|---|---|
| `app.py` | 애플리케이션 생성, 정적 프론트엔드 제공 |
| `backend/core/settings.py` | 디렉터리 경로·환경 설정 상수 정의 |
| `backend/api/` | 공유 서비스 조립과 Modules·Workflows·Artifact HTTP 라우터 |
| `backend/runtime/` | 모듈 등록소와 취소 가능한 격리 프로세스 실행기 |
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
