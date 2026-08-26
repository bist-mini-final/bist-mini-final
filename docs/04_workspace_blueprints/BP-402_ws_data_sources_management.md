# [BP-402] [구현됨] Data Sources Management 워크스페이스
> **Document Code:** `BP-402` | **Category:** Workspace Blueprint | **Status:** Implemented & Operational  
> **Source Directories:** [`frontend/src/features/data-sources/`](file:///c:/Repos/bist-mini-final/frontend/src/features/data-sources/), [`frontend/src/pages/DataSourcesPage.tsx`](file:///c:/Repos/bist-mini-final/frontend/src/pages/DataSourcesPage.tsx), [`backend/api/data_source_routes.py`](file:///c:/Repos/bist-mini-final/backend/api/data_source_routes.py)

---

## 1. 워크스페이스 개요 및 UI 구성 (Workspace Overview)

**Data Sources Management**는 엑셀 파일 업로드, 시트별 가시성 확인, Luna VLM 구조 감지 결과(바운딩 박스) 시각적 검증, 2D 셀 데이터 그리드 뷰어, 그리고 pgvector 인덱스 생성 및 상태 프로브를 수행하는 종합 데이터 엔지니어링 워크스페이스입니다.

```mermaid
flowchart TD
    subgraph ViewLayout ["DataSourcesView UI 구성 (Split-Pane Architecture)"]
        LEFT["좌측 패널: 워크북 & 파일 목록 (Upload, SHA-256 Hash, Status)"]
        TOP["상단 탭 바: 시트 선택기 (손익계산서, 재무상태표, 현금흐름표 등)"]
        CENTER["중앙 영역: Interactive Spreadsheet Grid & VLM Overlay Box"]
        RIGHT["우측 패널: pgvector Indexing Manager & Database Connection Probe"]
    end

    LEFT --> TOP
    TOP --> CENTER
    CENTER --> RIGHT
```

---

### 1.1 원자적 파이프라인 모듈과 백엔드 인프라의 결합 구조 (Module Composition)

`Data Sources Management`는 독립적인 **Layer 5 원자적 모듈들과 Layer 7 백엔드 스토리지 인프라를 유기적으로 조합**하여 엔드투엔드 엑셀 인제스천 파이프라인을 완성합니다:

| 계층 | 구성 요소 / 파일 경로 | 역할 및 협력 방식 |
| :--- | :--- | :--- |
| **Layer 5<br>(원자적 모듈)** | `structure.luna_vlm_structure_detector`<br>([`luna_vlm_structure_detector.py`](file:///c:/Repos/bist-mini-final/modules/structure/luna_vlm_structure_detector.py)) | • 엑셀 시트 이미지를 래스터라이징하여 GPT-5.6 Luna VLM으로 전송<br>• 표 경계(`TableBoundary`), 열 헤더, 행 스터브, 데이터 매트릭스 기하학 감지 |
| | `structure.cell_text_serializer`<br>([`cell_text_serializer.py`](file:///c:/Repos/bist-mini-final/modules/structure/cell_text_serializer.py)) | • 감지된 2D 좌표계를 단일 표준 규격(`header_with_value`) 텍스트 라인으로 직렬화 |
| | `retrieval.text_embedder`<br>([`text_embedder.py`](file:///c:/Repos/bist-mini-final/modules/retrieval/text_embedder.py)) | • 직렬화된 셀 텍스트를 `text-embedding-3-large`를 통해 **3072차원 고밀도 벡터**로 배치 임베딩 |
| **Layer 7<br>(스토리지 인프라)** | `backend/storage/pgvector_binary_copy.py` | • 3072차원 벡터와 메타데이터를 PostgreSQL `langchain_pg_embedding` 테이블로 **Binary COPY 프로토콜**을 통해 초고속 벌크 주입 |
| | `backend/storage/db_manager.py` | • PostgreSQL 커넥션 풀링 및 HNSW 인덱스 상태 헬스 프로브(`GET /api/data-sources/probe`) |

---

## 2. Luna VLM 시각적 바운딩 박스 오버레이 (VLM Overlay Rendering)

감지된 표 기하학(`TableBoundary`)을 원본 스프레드시트 캔버스 위에 CSS 하이라이트 박스로 렌더링합니다:

```mermaid
graph TD
    subgraph SheetCanvas ["시트 캔버스 오버레이 (Bounding Box Canvas)"]
        BOX["Table Boundary Box (Solid Slate Border, Alpha 0.1)"]
        HDR_COL["Column Header Box (Blue Alpha Tint, #3b82f6)"]
        HDR_ROW["Row Header Stub Box (Amber Alpha Tint, #f59e0b)"]
        DATA_MAT["Data Matrix Box (Green Alpha Tint, #10b981)"]
    end
```

- **상호작용 기능**: 사용자가 특정 테이블 경계 박스를 클릭하면 해당 테이블의 메타데이터(행 수, 열 수, 헤더 트리 계층)가 인스펙터에 표시되며, 오인식된 영역을 수동으로 보정할 수 있습니다.

---

## 3. 2단계 인제스천 & 사용자 피드백 분기점 (Two-Stage Ingestion & Review Checkpoint)

VLM의 잘못된 구조 인식이 벡터 스토어로 전파되는 것을 원천 차단하기 위해, 일괄 자동 실행 대신 **VLM 감지 후 사용자의 시각적 검증 및 승인을 거쳐 인덱싱을 진행하는 휴먼인더루프(Human-in-the-Loop) 분기점**을 적용합니다.

```mermaid
flowchart TD
    UPLOAD["1. 엑셀 워크북 업로드 및 시트 선택"] --> DETECT["2. Luna VLM 구조 감지 (POST /api/data-sources/detect-structure)"]
    DETECT --> OVERLAY["3. 그리드 위 바운딩 박스 시각적 렌더링 (헤더/스터브/데이터)"]
    
    subgraph ReviewCheckpoint ["★ 사용자 피드백 & 검증 분기점 (Human Review Checkpoint)"]
        OVERLAY --> USER_DECISION{"사용자 구조 검증"}
        USER_DECISION -- "구조 보정 필요" --> EDIT["바운딩 박스 드래그 수동 보정 / VLM 재감지"]
        EDIT --> OVERLAY
        USER_DECISION -- "구조 승인 (Confirm & Index)" --> PROCEED["사용자 승인 확인 (User Approved)"]
    end

    PROCEED --> INGEST["4. 확정 구조 기반 인덱싱 (POST /api/data-sources/ingest)"]
    
    subgraph IndexingPipeline ["5. 확정 인덱싱 파이프라인 (SSE 실시간 스트리밍)"]
        INGEST --> SERIAL["단일 표준 직렬화 (header_with_value)"]
        SERIAL --> EMBED["text-embedding-3-large (3072d 배치 임베딩)"]
        EMBED --> COPY["PostgreSQL Binary COPY 고속 주입"]
    end
```

---

### 3.1 단계별 실행 및 피드백 프로토콜

1. **Stage 1 (VLM 구조 감지 및 프리뷰)**:
   - 사용자가 워크북 시트를 선택하면 `POST /api/data-sources/detect-structure`를 호출하여 Luna VLM이 표 경계(`TableBoundary`), 열 헤더, 행 스터브를 감지하고 캔버스에 색상별 오버레이 박스를 렌더링합니다.
2. **중간 검증 분기점 (Human-in-the-Loop Review & Approval)**:
   - 사용자는 캔버스에서 감지된 헤더 계층 구조와 데이터 셀 영역을 시각적으로 확인합니다.
   - 오인식된 영역이 있을 경우 사용자가 직접 영역을 마우스로 보정할 수 있으며, 구조가 정확할 때만 **"구조 확정 및 색인 시작"** 버튼을 클릭합니다.
3. **Stage 2 (확정 구조 기반 벡터 인덱싱)**:
   - 사용자가 승인한 확정 좌표계를 바탕으로 `POST /api/data-sources/ingest`를 호출하여 직렬화 ➡️ 3072d 임베딩 ➡️ PostgreSQL Binary COPY 주입을 실행하며, SSE(`event: progress`)를 통해 진행률을 실시간 수신합니다.
4. **Database Connection Probe**:
   - 우측 상단 인디케이터가 페이지 진입(Mount) 시 `GET /api/data-sources/probe`를 단 1회 호출하여 PostgreSQL 및 pgvector 정상 가동 여부를 확인 및 표시합니다 (주기적 폴링 없음, 필요 시 새로고침 버튼으로 1회 수동 재조회).

---

## 4. 리팩토링 타깃 (Refactoring Targets)

1. **가상 스크롤(Virtual Scrolling) 그리드**:
   - As-Is: 1,000행 이상의 거대 시트 렌더링 시 DOM 노드 과다로 프레임 드롭 발생.
   - To-Be: `@tanstack/react-virtual`을 도입하여 뷰포트 내 가시 셀만 렌더링하는 가상화 그리드 적용.
2. **수동 바운딩 박스 드래그 편집기**:
   - VLM이 감지하지 못한 특수 레이아웃을 사용자가 마우스 드래그로 직접 영역 지정(Draw Bounding Box)할 수 있는 UI 툴킷 추가.
