# [BP-401] [구현됨] Pipeline Playground 워크스페이스
> **Document Code:** `BP-401` | **Category:** Workspace Blueprint | **Status:** Implemented & Operational  
> **Source Directories:** [`frontend/src/features/playground/`](file:///c:/Repos/bist-mini-final/frontend/src/features/playground/), [`frontend/src/pages/PlaygroundPage.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/pages/PlaygroundPage.tsx), [`backend/api/workflow_routes.py`](file:///c:/Repos/bist-mini-final/backend/api/workflow_routes.py)

---

## 1. 워크스페이스 개요 및 UI 결선도 (Workspace Overview)

**Pipeline Playground**는 개발자 및 연구자가 19개의 파이프라인 모듈을 시각적 2D 노드 그래프(React Flow) 상에서 자유롭게 배치하고 핀을 결선하여, 대기열(Queue) 지연 없이 **오직 Tier 1 동기식 인메모리 제로 I/O 엔진(`WorkflowExecutor`)을 통해 즉각적인 피드백을 얻는 고속 실험실(Interactive Laboratory / Sandbox)** 워크스페이스입니다.

```mermaid
flowchart TB
    subgraph UI_Canvas ["React Flow 2D Interactive Canvas (@xyflow/react)"]
        PALETTE["Module Sidebar Palette (19 Modules)"]
        CANVAS["Graph Canvas (Custom Workflow Nodes & Edges)"]
        INSPECTOR["Node Config Inspector & Parameter Tuner"]
        TRACE_PANEL["Execution Trace & I/O Inspector Panel"]
        SSE_BAR["Live SSE Run State & Progress Bar"]
    end

    subgraph ClientServices ["Playground Client Architecture"]
        CTX["PlaygroundStateContext (Zustand/React Context)"]
        ADAPTER["WorkflowGraphAdapter (React Flow <-> Backend DAG Model)"]
        API_CLIENT["Ky HTTP Client & EventSource SSE Streamer"]
    end

    PALETTE -->|Drag & Drop| CANVAS
    CANVAS -->|Select Node| INSPECTOR
    CANVAS -->|Run Pipeline| CTX
    CTX --> ADAPTER
    ADAPTER --> API_CLIENT
    API_CLIENT -->|POST /api/workflows/run| BACKEND["FastAPI /api/workflows"]
    BACKEND -.->|SSE Stream /api/workflows/runs/{id}/stream| API_CLIENT
    API_CLIENT --> SSE_BAR
    API_CLIENT --> TRACE_PANEL
```

---

## 2. React Flow 커스텀 노드 결선 명세 (Custom Node Architecture)

각 커스텀 노드(`CustomWorkflowNode`)는 모듈 카테고리에 따라 색상 톤과 핀아웃이 동적 렌더링됩니다:

| 모듈 카테고리 | 톤 및 테마 (Tone/Color) | 핸들 (Input/Output Handles) | 주요 노드 예시 |
| :--- | :--- | :--- | :--- |
| **Query** | 인디고 / 블루 (`tone-indigo`) | Target Handle 0~1개, Source Handle 1~2개 | `QueryInput`, `Decomposer`, `Router` |
| **Embedding** | 바이올렛 (`tone-violet`) | Target 1개 (Text), Source 1개 (Vectors) | `Embedder`, `CellTextEmbedder` |
| **Retrieval** | 에메랄드 / 그린 (`tone-green`) | Target 1~2개 (Embedding/Criteria), Source 1개 | `PgVectorRetriever`, `KeywordRetriever`, `RrfFusion` |
| **Context** | 앰버 / 옐로우 (`tone-amber`) | Target 1개 (Chunks), Source 1개 (Markdown) | `ContextExpander` |
| **Reader** | 로즈 / 레드 (`tone-rose`) | Target 2개 (Query + Context), Source 1개 (Answer)| `ReaderModule` |
| **Storage/VLM** | 시안 / 틸 (`tone-cyan`) | Target 1개, Source 1~2개 | `LunaVlmStructureDetector`, `IndexWriter` |

---

## 3. 실시간 실행 스트림 및 상태 동기화 프로토콜

1. 사용자가 **"파이프라인 실행"** 버튼을 클릭하면 `WorkflowGraphAdapter`가 React Flow 노드/엣지 객체를 백엔드 `WorkflowGraph` JSON으로 변환하여 전송합니다.
2. 백엔드로부터 `run_id`를 수신하면 `EventSource`를 열어 `/api/workflows/runs/{run_id}/stream`에 연결합니다.
3. 수신되는 이벤트(`node_started`, `node_completed`, `node_failed`)에 따라 해당 노드의 테두리에 실시간 로딩 스피너 및 성공/실패 뱃지가 표시됩니다.
4. 노드를 클릭하면 해당 노드의 입력 데이터, 출력 데이터, 실행 소요 시간(ms), 토큰 사용량이 `TracePanel`에 즉시 렌더링됩니다.

---

## 4. 리팩토링 타깃 (Refactoring Targets)

1. **`playground.css` 모듈화**:
   - As-Is: `playground.css` 파일이 80KB에 달하는 단일 거대 CSS 파일로 존재.
   - To-Be: 컴포넌트별 CSS Modules 또는 Tailwind CSS v4 유틸리티 클래스로 분할 리팩토링.
2. **템플릿 프리셋 갤러리**:
   - "기본 하이브리드 RAG", "VLM 엑셀 인덱싱 파이프라인", "재무 비율 직접 계산" 등 사전 정의된 원클릭 DAG 프리셋 로더 추가.
