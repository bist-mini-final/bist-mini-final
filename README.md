# RAG Flow Workbench

재무 질문 처리 모듈을 캔버스에서 조합하고, 사용자가 만든 DAG를 배치 단위로 실행하는 FastAPI + React 애플리케이션입니다.

저장소 루트가 곧 애플리케이션 루트입니다. 별도의 중간 프로젝트 디렉터리를 두지 않습니다.

## 구조 원칙

- `app.py`: 애플리케이션 생성과 정적 프론트엔드 제공만 담당합니다.
- `backend/answer_cache.py`: 사용자 질문과 최종 답변 캐시의 영속화만 담당합니다.
- `backend/similarity.py`: 문자열 유사도 계산만 담당합니다.
- `backend/routes.py`: 도메인별 HTTP 라우터 조립만 담당합니다.
- `backend/api/module_routes.py`: 독립 모듈 조회와 실행 API를 담당합니다.
- `backend/api/workflow_routes.py`: 워크플로 저장과 run 실행 API를 담당합니다.
- `backend/modules`: 프론트 노드와 1:1로 대응하는 Python 실행 모듈입니다.
- `backend/spreadsheets`: processed Excel 탐색, 원본 스타일 PNG 렌더링, BFS 표 분리, 계층 헤더 구성, Docling 좌표 변환을 역할별로 제공합니다.
- `backend/vector_index_store.py`: 콘텐츠 주소형 exact cosine 인덱스와 셀 메타데이터의 영속 저장·검색을 담당합니다.
- `backend/module_registry.py`: 모듈 조회와 독립 실행 진입점을 제공합니다.
- `backend/workflows/models.py`: 캔버스, 연결, run, 노드 상태 JSON 스키마를 정의합니다.
- `backend/workflows/store.py`: 워크플로·run·결과 캐시를 원자적으로 저장합니다.
- `backend/workflows/executor.py`: 포트 검증, 위상 배치, 순환 검출, 실행 재개를 담당합니다.
- `frontend/src/services`: API 통신을 한곳에서 관리합니다.
- `frontend/src/hooks`: 파이프라인 실행 상태와 그래프 편집 상태를 분리해 관리합니다.
- `frontend/src/config`: 단계·모듈 메타데이터를 단일 소스로 관리합니다.
- `frontend/src/components/FlowNode/NodeShell.tsx`: 모든 그래프 노드의 공통 구조와 상태 표현을 제공합니다.
- `frontend/src/index.css`: 디자인 토큰과 반응형 규칙을 관리합니다.
- `tests`: 현재 백엔드 도메인과 데이터 통합 테스트를 관리합니다.
- `data/workflows`: 버전 관리되는 기본 템플릿과 로컬 사용자 워크플로 정의입니다.
- `data/runs`: 실행별 입력·출력·상태가 저장되는 런타임 디렉터리입니다.
- `data/cache`: 모듈 타입·버전·입력으로 계산한 결과 캐시입니다.
- `data/vector_db`: 재사용 가능한 문서 벡터 인덱스와 메타데이터입니다.

## 실행과 검증

```bash
cd frontend
npm run dev
npm run build

cd ..
python3 -m uvicorn app:app --host 127.0.0.1 --port 8765
python3 -m unittest discover -s tests

# 로컬 멀티모달 표 구조 모듈
ollama pull qwen3-vl:4b-instruct
```

프론트엔드 빌드는 엄격한 TypeScript 검사를 먼저 실행합니다. 작은 화면에서는 모듈 라이브러리가 캔버스를 가리지 않는 드로어로 전환되며, 모듈 카드를 터치해 바로 추가할 수 있습니다. 노드 위치, 연결, 모듈 설정, 뷰포트는 700ms 디바운스로 자동 저장되며 수동 저장 버튼도 제공합니다.

## 모듈 실행 계약

프론트엔드는 `GET /api/modules`에서 모듈 이름, 설명, 입력 및 출력 계약을 읽습니다. 각 모듈은 다음 API로 독립 실행할 수 있습니다.

```text
POST /api/modules/{module_type}/execute
```

예를 들어 `embedder`는 `question_id`와 `subqueries`를 최상위 필드로 입력받아 서브쿼리별 실제 숫자 임베딩을 `items`로 반환합니다. 기본 파이프라인 역시 같은 모듈 레지스트리를 순서대로 실행하므로, 화면용 데이터와 독립 실행 결과가 서로 다른 코드 경로를 사용하지 않습니다.

| 프론트 노드 | 백엔드 실행 파일 | 입력 | 출력 |
|---|---|---|---|
| Query Input | `backend/modules/query_input.py` | `query` | `cached_answer` 또는 `question_text` |
| Decomposer | `backend/modules/decomposer.py` | `question_text` | `question_id`, `subqueries` (평탄 DTO) |
| Embedder | `backend/modules/embedder.py` | `question_id`, `subqueries` | `question_id`, `items{subquery: embedding}` |
| BM25 Retriever | `backend/modules/bm25_retriever.py` | `query_input{question_id, subqueries}` + `document_input{Excel 셀 문서}` | 서브쿼리별 실제 Okapi BM25 후보 순위 |
| Cell Text Embedder | `backend/modules/cell_text_embedder.py` | Structured Cell Text Serializer 출력 | 셀 메타데이터, `embedding_index`, float32 아티팩트 참조 |
| Vector Index Writer | `backend/modules/vector_index_writer.py` | Cell Text Embedder 출력 | 영속 `index_id`, 모델·차원·문서 개수 |
| Dense Retriever | `backend/modules/dense_retriever.py` | `query_input{서브쿼리 임베딩}` + `index_input{index_id}` | 서브쿼리별 실제 코사인 유사도 후보 순위 |
| RRF Fusion | `backend/modules/rrf_fusion.py` | `bm25_result`, `dense_result` | 동일 서브쿼리별 rank 결합 후 셀 단위 Top-K |
| Context Expander | `backend/modules/context_expander.py` | `retrieval_json` + Serializer `document_input` | 같은 시트 인접 ±N행의 전체 열 실제 값 |
| Reader | `backend/modules/reader.py` | `question_text` + `context_json` | 실제 LLM이 생성한 근거 기반 `answer_json` |
| Answer Cache Writer | `backend/modules/answer_cache_writer.py` | `question_text` + Reader `answer_json` | 답변 캐시에 저장한 동일 `answer_json` |
| JSON Transformer | `backend/modules/json_transformer.py` | `any_json` | `transformed_json` |
| JSON Inspector | `backend/modules/json_inspector.py` | 원본 JSON | 원본 JSON |
| Processed Excel Selector | `backend/modules/processed_file_selector.py` | 설정의 `file_name` | `file_name`, `workbook_hash`, `sheet_names` |
| BFS + LLM Structure Detector | `backend/modules/bfs_llm_structure_detector.py` | 선택된 workbook DTO | `title`, `column_header`, `row_header`, `data` 영역과 좌표 기반 `header_tree` |
| Local VLM Structure Detector | `backend/modules/local_vlm_structure_detector.py` | 선택된 workbook DTO | 셀 타입 이미지와 좌표 컨텍스트로 식별한 공통 spreadsheet structure DTO |
| Luna Full-Sheet Structure Detector | `backend/modules/luna_vlm_structure_detector.py` | 선택된 workbook DTO | 후보 필터 없이 전체 표시 시트를 타일 분석·병합한 공통 spreadsheet structure DTO |
| Docling Table Detector | `backend/modules/docling_table_detector.py` | 선택된 workbook DTO | `sheet_name`과 영역 JSON을 가진 평탄 `tables[]` |
| OpenPyXL Region Classifier | `backend/modules/openpyxl_region_detector.py` | Docling의 평탄 `tables[]` | 제목·헤더·데이터 영역과 좌표 기반 `header_tree`를 가진 `tables[]` |
| Structured Cell Text Serializer | `backend/modules/cell_text_serializer.py` | 공통 spreadsheet structure DTO | 셀별 `header_only`, `header_with_value` 검색 문서 |
| Exhaustive Cell Header Serializer | `backend/modules/exhaustive_cell_text_serializer.py` | 선택된 workbook DTO | 모든 표시 값 셀의 왼쪽 × 위쪽 헤더 후보 조합 문서 |

스프레드시트 흐름은 `data/processed` 내부 파일만 선택할 수 있습니다. 숨김 시트와 숨김 또는 높이·너비 0인 행·열은 애플리케이션 전체에서 존재하지 않는 데이터로 취급합니다. 파일 선택, 원본 렌더링, 셀 타입 컨텍스트, BFS, Docling 좌표 변환, OpenPyXL 분류, 헤더 트리, Serializer 어느 단계에서도 해당 셀 값을 읽거나 중간 DTO와 캐시에 포함하지 않습니다. 그룹으로 접힌 열에도 같은 규칙이 적용됩니다. 기본 DAG는 `Processed Excel Selector → Local VLM Table Structure Detector → Structured Cell Text Serializer`를 사용합니다. Local VLM 모듈은 원본 스타일 렌더링 위에 값 셀을 text·number·date·boolean·error 타입별로 반투명 채색하고 수식 셀에는 별도 테두리를 표시합니다. 이미지와 함께 모든 표시 값 셀의 Excel 좌표·타입·값·수식·병합 범위를 압축 JSON으로 로컬 Ollama에 전달합니다. 기본 모델은 `qwen3-vl:4b-instruct`이며 외부 LLM API 비용은 발생하지 않습니다. 응답은 strict JSON Schema로 제한하고 시트 범위, 테이블 포함관계, 제목·헤더·데이터의 상대 위치를 검증합니다. 모델이 선언한 헤더 행과 데이터 경계는 유지하면서 공통 직사각형 DTO가 전체 데이터 열·행을 덮도록 정규화합니다. 타입 오버레이는 `data/artifacts/spreadsheets/{hash}/typed`에 저장되어 노드의 돋보기에서 확인할 수 있으며, 검사 창에서는 셀 타입 색상과 영역 분류 박스를 독립적으로 켜고 끌 수 있습니다.

BFS + LLM 모듈도 비교 가능한 대체 노드로 캔버스에 유지합니다. 이 모듈은 비어 있지 않은 셀의 4방향 연결요소를 구하고 가까운 영역을 병합한 뒤 각 표 상단 최대 10행만 LLM에 배치 전달합니다. LLM은 제목 마지막 행·데이터 시작 행·좌측 인덱스 열 수만 판단하고, 실제 계층 헤더 트리는 병합 셀 좌표의 포함 관계로 결정적으로 구성합니다.

다섯 가지 구조 추출 노드(Docling, OpenPyXL, BFS + LLM, Local VLM, Luna Full-Sheet)는 헤더의 같은 위치에 결과 검사 돋보기 버튼을 제공합니다. 실행 전에는 비활성 안내를 표시하고 실행 후에는 시트별 테이블·제목·열 헤더·행 헤더·데이터 bbox와 계층 헤더를 공통 팝업에서 확인할 수 있습니다. Docling은 원본/주석 이미지를, 두 VLM 모듈은 원본/셀 타입 오버레이를 전환할 수 있으며 모듈별 색상과 아이콘으로 결과 출처를 구분합니다.

Luna Full-Sheet 모듈은 테이블 후보 bbox나 타일을 사용하지 않습니다. 숨김 축을 제거한 표시 시트 전체를 원본 스타일과 셀 타입·좌표 라벨이 함께 있는 이미지 한 장으로 만들고, 전체 좌표·타입·값 컨텍스트와 함께 OpenAI Responses API에 시트당 한 번 전달합니다. 모델 응답의 모든 범위를 전체 시트 좌표 안에서 검증하고 바로 공통 `tables[]` DTO로 조립하므로 Structured Cell Text Serializer 앞에 연결할 수 있습니다. 구조 추론에서는 일반 설명형 텍스트를 제목·열/행 헤더의 강한 힌트로 사용하되, 데이터 행렬 위치의 `NA`, `N/A`, `NM`, 대시 같은 결측·상태 표시는 텍스트 타입이어도 데이터로 유지합니다. 이 공통 규칙은 Luna, Local VLM, BFS + LLM 모듈에 동일하게 적용됩니다.

기존 `Docling Table Detector → OpenPyXL Region Classifier`는 비교·대체 가능한 독립 경로로 유지합니다. Docling 모듈은 Excel 시트를 PNG로 렌더링하고 테이블 bbox를 셀 범위로 변환하며, OpenPyXL 모듈은 서식뿐 아니라 숫자 밀도·기간 헤더·좌측 텍스트 열을 함께 분석합니다. 두 경로 모두 `spreadsheet_structure.py`의 같은 출력 DTO를 사용하므로 Serializer 앞에서 자유롭게 교체할 수 있습니다. 렌더러는 PixelRAG의 정규화 HTML 테마를 복제하지 않고 원본 workbook의 열 너비, 행 높이, 병합, fill, font 색상·굵기·기울임, border, alignment, number format과 줄바꿈을 보존하며 셀↔픽셀 좌표 정합성을 유지합니다. 렌더링·주석 이미지는 재생성 가능한 `data/artifacts`에 저장됩니다. macOS 기본 Python 3.9에서는 Docling의 OCR 의존성과 호환되도록 `requirements.txt`가 PyObjC 11.1을 고정합니다.

Structured Cell Text Serializer는 공통 구조 DTO의 `title`, `column_header`, `row_header`, `data` 영역을 실제 workbook 값과 결합합니다. 숨겨진 행·열과 빈 셀을 제외하고 병합 셀의 대표 값을 해석한 뒤, 제목과 행 헤더를 상위 수준부터 보존하고 각 셀을 `Sheet: ... | Row Header: ... | Column Header: ... | Cell Value: ...` 순서로 고정합니다. 셀마다 값이 `?`인 `header_only`와 실제 값이 포함된 `header_with_value` 두 문서를 생성합니다.

구조 추론을 사용하지 않는 대체 경로는 `Processed Excel Selector → Exhaustive Cell Header Serializer → BGE Cell Text Embedder → Vector Index Writer`입니다. Exhaustive Serializer는 숨겨지지 않은 모든 값 셀을 데이터 셀로 취급하고, 같은 행에서 왼쪽에 있는 모든 값과 같은 열에서 위쪽에 있는 모든 값의 데카르트 곱을 공통 Structured Cell DTO로 생성합니다. 기본값은 질의의 헤더 표현과 직접 비교하는 `header_only`이며 동일한 헤더 값은 같은 직렬화 문장을 만들기 때문에 한 번만 생성합니다. 좌표별 중복까지 필요한 경우 설정에서 병합을 끌 수 있습니다. 조합 수가 안전 한도를 넘으면 일부만 잘라 저장하지 않고 실행을 실패시키므로 설정에서 한도를 명시적으로 조정해야 합니다. 생성 결과는 다른 직렬화기와 같은 DTO이므로 기존 임베딩·BM25·컨텍스트 경로를 그대로 사용할 수 있습니다.

직렬화 모듈 노드는 대상 셀 수와 생성 문서 수만 요약합니다. 실제 데이터 미리보기는 JSON Inspector의 단일 역할이며, 상류 모듈 타입별 어댑터를 사용합니다. Structured Cell DTO가 연결되면 검색 메타데이터를 별도 열로 펼치지 않고 `text` 필드만 임의 5행으로 표시하고, Reader DTO가 연결되면 `answer` 필드만 GFM Markdown 답변 카드로 표시합니다. Inspector의 백엔드 출력은 어떤 뷰를 사용하더라도 입력 JSON 원본을 그대로 통과시킵니다.

문서 임베딩의 숫자 벡터 본문은 워크플로 실행 JSON에 넣지 않습니다. Cell Text Embedder가 `data/artifacts/embeddings`의 콘텐츠 주소형 float32 파일로 저장하고 출력 DTO에는 참조만 전달합니다. Vector Index Writer는 이 아티팩트를 정규화된 float32 행렬과 셀 메타데이터로 한 번 저장하며, Dense Retriever는 `index_id`만 받아 exact cosine 검색을 수행합니다. 인덱스 ID에는 포맷 버전과 임베딩 아티팩트 ID가 반영되어 workbook·문서 텍스트·모델이 바뀌면 새 인덱스가 생성됩니다. API 프로세스에는 FAISS/OpenMP를 로드하지 않아 Torch 계열 모듈과 함께 실행할 때의 네이티브 런타임 충돌을 피합니다.

검색은 참조 `rag-rdb-poc`과 같은 의미 순서를 따릅니다. 각 서브쿼리마다 BM25와 Dense 순위를 만든 뒤 같은 서브쿼리의 rank만 RRF로 합산하고, dual-view 표현을 Cell ID로 축약해 최종 Top 100을 선택합니다. 비율 의도가 없는 질문의 margin·ratio 행은 기본 `ratio_penalty=0.4`가 적용됩니다. Context Expander는 RRF Top 100을 기준으로 같은 시트의 인접 ±3행과 모든 열의 실제 값을 복원하고, Reader는 이 컨텍스트와 원문 질문만으로 답변과 Cell ID 인용을 생성합니다.

Decomposer의 프리셋과 System/User 프롬프트는 노드 설정에서 관리합니다. 사용자가 입력한 질문은 기존 평가 질문이나 저장된 서브쿼리를 조회하지 않고 OpenAI 호환 Chat Completions API로 바로 분해합니다. 프로젝트 루트 `.env`의 `OPENAI_API_KEY`와 선택적인 `OPENAI_BASE_URL`을 읽으며 설정 예시는 `.env.example`에 있습니다. 출력은 안정적인 `question_id`와 최종 `subqueries`만 포함합니다. API 호출이나 JSON 포맷 검증에 실패하면 임의 출력을 만들지 않고 해당 노드가 실패합니다.

## 워크플로 저장 형식

기본 캔버스 템플릿은 [`data/workflows/default.json`](data/workflows/default.json)에 저장됩니다. 애플리케이션은 로컬 `data/workflows/workflow.json`을 우선 사용하고, 파일이 없을 때만 `default.json`으로 폴백합니다. 사용자가 캔버스를 저장하면 이후 변경은 Git에서 제외된 `workflow.json`에 기록되며 `default.json` 템플릿은 수정하지 않습니다. JSON에는 실행 결과를 섞지 않고 다음 편집 정보만 둡니다.

- `schema_version`, 워크플로 ID와 이름
- 노드 ID, Python 모듈 타입, 위치, 모듈 설정
- `values`: Query Input처럼 새로고침 후 복원할 사용자 입력 초안
- `ui`: Inspector처럼 사용자가 조절한 노드 너비 등 캔버스 표현 정보
- 연결 ID, 시작/도착 노드, 선택적인 출력·입력 포트
- 캔버스 이동과 확대/축소 값

파일을 외부 편집기로 수정한 뒤 서버를 다시 시작해도 같은 그래프가 복원됩니다. 여러 출력 또는 입력 포트를 갖는 모듈은 연결의 `source_output`, `target_input`을 명시합니다. 입출력 포트가 각각 하나뿐인 경우에만 생략 시 자동 추론합니다.

```text
GET  /api/workflows/{workflow_id}
PUT  /api/workflows/{workflow_id}
GET  /api/workflows
```

## 배치 DAG 실행과 상태 전달

실행을 만들면 워크플로 정의 전체가 run에 스냅샷으로 복사됩니다. 실행 도중 캔버스를 수정해도 이미 시작된 run의 의미는 바뀌지 않습니다.

1. 실행기는 모든 연결과 포트를 검증하고 순환을 거부합니다.
2. 위상 깊이가 같은 준비된 노드를 하나의 배치로 묶습니다.
3. 노드 설정과 런타임 입력, 선행 노드의 명명된 출력을 합쳐 입력을 만듭니다.
4. 노드 실행 전후마다 `data/runs/{run_id}.json`을 원자적으로 갱신합니다.
5. 다음 배치는 파일에 저장된 선행 출력을 다시 읽어 입력 포트로 전달합니다.
6. 서버가 중단되면 `running` 상태만 `pending`으로 되돌리고, 이미 성공한 노드 출력은 그대로 사용해 이어서 실행합니다.

평가셋 전용 고정 파이프라인 API는 제공하지 않습니다. 실제 결과를 만드는 경로는 저장된 DAG run 하나로 통일되어 있습니다. 모듈의 재생 버튼은 선택한 노드 하나만 실행하며, 같은 배치의 다른 노드는 건드리지 않습니다. 다시 실행한 노드의 하위 노드는 이전 입력에 기반한 결과만 무효화되고 자동 실행되지 않습니다. 전체 자동 실행은 기존 배치 단위 위상 실행을 유지합니다. Query Input의 `threshold`는 연결 입력이 아니라 노드 `config`에만 저장되며, 실행 시에는 사용자가 작성한 `query`만 런타임 입력으로 전달됩니다.

결정적 모듈은 `module_type + version + input`의 SHA-256 키로 결과를 캐시합니다. 랜덤 샘플 로더처럼 비결정적인 모듈은 캐시 대상에서 제외됩니다.

Reader는 답변 생성만 담당하고 캐시 저장 부작용을 숨기지 않습니다. 기본 DAG의 Answer Cache Writer가 원문 질문과 Reader 출력을 받아 명시적으로 저장하며, 이후 Query Input은 유사도 임계값을 만족하는 질문에 `cached_answer` 분기를 반환합니다. Writer는 부작용 모듈이므로 결과 캐시 대상에서 제외됩니다.

```text
POST /api/workflows/{workflow_id}/runs   # run 생성
POST /api/runs/{run_id}/nodes/{node_id}/execute # 선택한 노드 하나만 실행
POST /api/runs/{run_id}/cancel          # 실행 중인 격리 모듈 프로세스 즉시 종료
POST /api/runs/{run_id}/execute-next    # 준비된 다음 배치 실행
POST /api/runs/{run_id}/execute         # 남은 모든 배치 실행
POST /api/runs/{run_id}/resume          # 실패 노드 재시도 후 이어서 실행
GET  /api/runs/{run_id}                 # 저장된 노드 입출력과 상태 조회
GET  /api/runs?workflow_id={id}          # 워크플로 실행 이력 조회
DELETE /api/cache                        # 결과 캐시와 run 이력 삭제, 워크플로 보존
```

`data/runs`, `data/cache`, `data/processed`는 로컬 실행 데이터라 Git에서 제외합니다. `data/workflows/default.json`만 기본 템플릿으로 저장소에 포함하고, 사용자가 편집하는 `data/workflows/workflow.json`은 Git에서 제외합니다.

현재 모듈은 읽기 또는 결정적 변환 중심입니다. 향후 외부 결제·메시지 발송처럼 부작용이 있는 모듈을 추가할 때는 프로세스 중단 직후 재시도될 수 있는 at-least-once 실행을 전제로 멱등성 키를 모듈 내부에서 처리해야 합니다.
