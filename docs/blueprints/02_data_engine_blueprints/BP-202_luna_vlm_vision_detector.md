# [BP-202] Luna VLM 이미지 렌더링 & 표 바운딩박스 검출 회로
> **Document Code:** `BP-202` | **Category:** Data Engine & Vision Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`modules/structure/luna_vlm_structure_detector.py`](file:///c:/Repos/bist-mini-final/modules/structure/luna_vlm_structure_detector.py), [`backend/storage/spreadsheets/sheet_renderer.py`](file:///c:/Repos/bist-mini-final/backend/storage/spreadsheets/sheet_renderer.py), [`backend/storage/spreadsheets/cell_type_overlay.py`](file:///c:/Repos/bist-mini-final/backend/storage/spreadsheets/cell_type_overlay.py)

---

## 1. Luna VLM 구조 감지 아키텍처 (Luna VLM Vision Architecture)

엑셀 파일 내의 표는 복잡한 서식, 텍스트 메모, 다중 표 병합 등으로 인해 순수 텍스트 파싱만으로는 표의 경계를 정확히 잡기 어렵습니다. `LunaVlmStructureDetectorModule`은 **시트 래스터라이징(Rasterization)과 GPT-5.6 Luna 추론**을 결합하여 완벽한 표 바운딩 박스를 도출합니다.

```mermaid
sequenceDiagram
    autonumber
    participant Parser as LunaVlmStructureDetectorModule
    participant Renderer as ExcelSheetRenderer (Pillow)
    participant VLM as OpenAIResponsesClient (GPT-5.6 Luna)
    participant Disk as Spreadsheet Artifact Storage (/data/artifacts)

    Parser->>Renderer: render_sheet_image(workbook, sheet_name, max_rows=100, max_cols=30)
    Renderer->>Renderer: 폰트 렌더링, 셀 그리드 라인, 숫자/텍스트 색상 오버레이 합성
    Renderer->>Disk: PNG 이미지 저장 (sheet_preview_hash.png)
    Renderer-->>Parser: Base64 Encoded Image Data

    Parser->>VLM: structured_chat_completion(image_payload, prompt=TABLE_DETECTION_PROMPT)
    Note over VLM: 표 바운딩박스, 열 헤더 범위, 행 헤더(스터브) 범위, 데이터 영역 추론
    VLM-->>Parser: JSON Structured Output (SheetLayout & TableBoundaries)

    Parser->>Parser: 기하학적 유효성 검증 (CellBounds overlap check)
    Parser-->>Parser: SheetLayout 객체 확정 및 캐싱
```

---

## 2. 시각적 오버레이 합성 파이프라인 (Cell Type Visual Overlay)

`ExcelSheetRenderer`는 GPT-5.6 Luna 모델의 인식 정확도를 극대화하기 위해 셀 데이터 타입별 시각적 힌트를 캔버스에 그립니다:

| 셀 데이터 타입 | 시각적 렌더링 스타일 (Rendering Style) | VLM 인식 보조 효과 |
| :--- | :--- | :--- |
| **Header Text** | 볼드체, 진한 배경색(Dark Slate), 상하 테두리 강조 | 테이블 및 열/행 헤더 영역 즉각 분별 |
| **Numeric Values**| 우측 정렬, 연한 청색 배경 오버레이 | 데이터 매트릭스(Data Region) 자동 영역화 |
| **Merged Cells** | 테두리 박스 및 중심 텍스트 앵커링 | 다층 복합 헤더 트리 계층 관계 복원 |
| **Units & Notes** | 이탤릭체, 작은 폰트(Small Grey) | 테이블 메타데이터(단위: 백만원, 삼일회계법인 등) 격리 |

---

## 3. VLM 출력 스키마 및 바운딩 박스 모델

```mermaid
classDiagram
    class SheetLayout {
        +str sheet_name
        +int total_rows
        +int total_cols
        +List~TableBoundary~ tables
    }

    class TableBoundary {
        +str table_id
        +str table_type
        +CellBounds bounding_box
        +CellBounds column_header_range
        +CellBounds row_header_range
        +CellBounds data_range
    }

    class CellBounds {
        +int start_row
        +int start_col
        +int end_row
        +int end_col
        +to_excel_range() str
    }

    SheetLayout *-- TableBoundary
    TableBoundary *-- CellBounds
```

---

## 4. 프롬프트 엔지니어링 및 무오염 Fail-Fast 원칙 (Prompt Guidance & Fail-Fast Policy)

1. **테이블 단일화 가이드라인 (`TABLE_UNIFICATION_GUIDANCE`)**:
   - 빈 행 1~2개로 구분된 인접 블록이라도 계정과목과 기간 축이 동일하면 단일 테이블로 통합 감지하도록 프롬프트 지시.
2. **엄격한 데이터 무결성 보장 및 Fail-Fast 원칙 (Zero-Heuristic Fail-Fast)**:
   - **사일런트 휴리스틱 폴백 전면 금지**: 임의로 "첫 행=헤더, 첫 열=스터브"로 대충 때려 맞추는 휴리스틱 폴백은 복합 재무제표의 계층 구조를 심각하게 파괴하고 벡터 DB를 오염(Garbage-In)시킵니다.
   - **재시도 및 즉시 중단(Fail-Fast)**: VLM API 호출 실패 또는 네트워크 지연 시 `BaseLLMModule` 계층에서 최대 3회 지수 백오프(Exponential Backoff) 재시도를 수행하며, 최종 실패 시 **`ProviderApiError`를 발생시키고 파이프라인을 즉시 중단(Fail-Fast)**하여 오염된 데이터가 인덱싱되는 것을 원천 차단합니다.

---

## 5. 리팩토링 타깃 (Refactoring Targets)

1. **로컬 VLM 경량화 모델 지원 — 범위 제외 (Out of Scope)**:
   - 현재 및 계획 기준선은 OpenAI GPT-5.6 Luna 클라우드 API를 사용한다.
   - `Qwen2-VL-7B`, `PaliGemma-2`, ONNX/vLLM 기반 로컬 추론과 에어갭 배포는 이 프로젝트의 구현 범위에 포함하지 않는다.
2. **동적 타일링(Dynamic Image Tiling)**:
   - 100행 이상의 거대 시트를 균등 분할 렌더링하고, 바운딩 박스 좌표를 합성하는 Multi-Tile VLM 결합 알고리즘 도입.
