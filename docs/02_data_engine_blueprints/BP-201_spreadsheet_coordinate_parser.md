# [BP-201] 2D 그리드 셀 좌표계 파서 & 마크다운 직렬화
> **Document Code:** `BP-201` | **Category:** Data Engine Blueprint | **Status:** Approved Baseline  
> **Source Files:** [`backend/storage/spreadsheets/`](file:///c:/Repos/bist-mini-final/backend/storage/spreadsheets/), [`modules/structure/cell_text_serializer.py`](file:///c:/Repos/bist-mini-final/modules/structure/cell_text_serializer.py)

---

## 1. 2D 스프레드시트 파싱 및 좌표계 정규화 (Coordinate Parsing Engine)

기업 재무 엑셀은 **병합 셀(Merged Cells), 빈 행/열, 숨김 시트(Hidden Sheets), 다층 복합 헤더(Multi-level Headers)**를 포함하고 있어 단순 CSV 형태로는 RAG 색인이 불가능합니다. `bist-mini-final`은 2D 그리드 좌표계를 완벽히 정규화하는 파싱 파이프라인을 갖추고 있습니다.

```mermaid
flowchart LR
    XLSX["Raw Excel File (.xlsx)"] --> LOAD["OpenPyXL Data-Only Loader"]
    LOAD --> VIS["Hidden Sheet Filter (state != 'hidden')"]
    VIS --> MERGE["Merged Cell Value Broadcast"]
    MERGE --> NORM["2D Sparse Grid Coordinate Mapper (A1 -> [row, col])"]
    NORM --> SERIAL["Structured Cell Text Serializer"]
    SERIAL --> CHUNK["Dense & Sparse Search Chunks"]
```

---

## 2. 병합 셀 브로드캐스팅 및 좌표 정규화 규칙

1. **병합 셀 값 전파 (Merged Cell Broadcast)**:
   - 병합 영역 `A1:C1`에 "재무상태표 (2023)" 값이 있을 때, 실제 데이터 추출 시 `A1`, `B1`, `C1` 전체에 부모 헤더 문맥을 전파하여 검색 시 누락을 방지합니다.
2. **2D 직교 좌표계 표준화 (Zero-Hardcoding)**:
   - `Row Index`: 1-indexed 양의 정수 (예: `1`, `2`, `100`)
   - `Column Index / Letter`: 1-indexed 정수 및 영문 알파벳 좌표 (예: `1` ↔ `A`, `27` ↔ `AA`)
   - **원본 시트명 보존 (Raw Sheet Identity)**:
     - 엑셀마다 `포괄손익계산서(연결)`, `Income Statement`, `3.재무상태표`, `Sheet1` 등 임의의 명칭이 들어오므로, **불안정한 하드코딩 정적 매핑(`손익계산서->IS`)을 전면 배제**합니다.
     - 원본 시트명 문자열(`sheet_name: str`)과 시트 순환 인덱스(`sheet_index: int`)를 단일 진실 원천(SSOT)으로 그대로 보존하며, 표준 재무제표 분류가 필요할 경우 **Luna VLM / LLM 구조 분석기가 시트 내용과 헤더를 종합 분석하여 동적으로 시맨틱 태깅**합니다.

---

## 3. Structured Cell Text 직렬화 포맷 (Serialization Grammar)

각 수치 셀은 단독으로는 의미를 알 수 없으므로, 계층적 헤더 문맥과 결합된 **대칭적 검색 문자열(Structured Cell Text)**로 직렬화됩니다.

### 직렬화 표준 EBNF 문법
```text
StructuredChunk ::= "Company: " CompanyName " | Sheet: " SheetName 
                    " | Row Header: " RowHierarchy 
                    " | Column Header: " ColumnHierarchy 
                    " | Cell Value: " Value [" | Unit: " UnitName]
```

### 직렬화 실례
- **입력 셀 위치**: `손익계산서!C5` (값: `65670`)
- **감지된 헤더**: 행 헤더 = `[영업수익, 매출총이익, 영업이익]`, 열 헤더 = `[제 55기, 2023]`
- **최종 직렬화 텍스트**:
  ```text
  Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670
  ```

---

## 4. 직렬화 변형 모드 및 계층 구조 보존 (Serializer Variant Modes)

검색(Retrieval) 단계와 LLM 생성(Generation) 단계의 목적에 맞추어 3가지 직렬화 변형 모드를 지원합니다:

| 모드명 | 직렬화 형식 | 목적 및 최적화 대상 |
| :--- | :--- | :--- |
| **`header_with_value`** | `Company: ... \| Sheet: ... \| Row: [대분류 > 소분류] \| Col: ... \| Value: ...` | **[기본값]** pgvector Dense 벡터 검색(3072d) 및 단일 셀 매칭 |
| **`row_block_markdown`** | 다층 복합 헤더와 상하위 계층 경로가 온전히 보존된 **2D 마크다운 표 블록** | **[LLM Reader 전용]** Context Expander가 주입하는 최적의 추론 문맥 |
| **`hierarchical_key_value`**| `삼성전자.포괄손익계산서[2023].영업수익.영업이익 = 65670 (단위: 백만원)` | Native BM25 tsvector 키워드 FTS 정확 일치 검색 |

---

### 4.1 `row_block_markdown`의 계층 구조 보존 방식 (Hierarchical Context-Preserving Markdown)

단순한 1차원 플랫 테이블이 아니라, **상위 계층 부모 경로(Parent Category Hierarchy), 다중 복합 열 헤더, 통화 단위, 인접 $\pm 2$행 이웃 문맥(2D Neighbor Context)**을 결합하여 LLM이 완벽한 시각적/구조적 관계를 인식할 수 있도록 포맷팅됩니다:

```markdown
<!-- [Context Expander 2D Markdown Block] -->
**[회사]** 삼성전자 | **[시트]** 포괄손익계산서(연결) | **[단위]** 백만원

| 계정과목 (계층 경로) | 제 54기 (2022.12) | 제 55기 (2023.12) |
| :--- | :---: | :---: |
| Ⅰ. 매출액 (영업수익) | 302,231,360 | 258,935,494 |
| Ⅱ. 매출원가 | (190,041,120) | (178,204,400) |
| Ⅲ. 매출총이익 | 112,190,240 | 80,731,094 |
| Ⅳ. 판매비와관리비 | (68,819,950) | (74,163,894) |
| **Ⅴ. 영업이익 (포커스 셀)** | **43,370,290** | **6,567,200** |
| &nbsp;&nbsp; 1. 국내영업이익 | 31,200,100 | 4,210,000 |
| &nbsp;&nbsp; 2. 해외영업이익 | 12,170,190 | 2,357,200 |
```

1. **상하위 트리 경로 보존**: 하위 항목(`국내영업이익`)은 부모(`Ⅴ. 영업이익`) 아래 들여쓰기(`&nbsp;` 또는 경로 표기)되어 상하 관계를 보존합니다.
2. **다층 복합 열 헤더 결합**: 기수(`제 55기`)와 결산연월(`2023.12`)이 하나의 정규화된 열 헤더로 합성되어 시계열 비교 왜곡을 방지합니다.
3. **2D 공간 확장 (Context Expansion)**: 검색된 단일 셀(`6,567,200`)만 달랑 주지 않고, 상하위 계정과목과 직전 연도 비교 열을 직사각형 블록으로 함께 제공하므로 LLM이 할루시네이션 없이 정확한 추론을 수행합니다.

---

## 5. 리팩토링 타깃 (Refactoring Targets)

1. **대용량 시트 메모리 최적화**:
   - As-Is: OpenPyXL 전체 메모리 로드 (`load_workbook(data_only=True)`). 100MB 이상 엑셀에서 메모리 스파이크 발생 가능.
   - To-Be: `read_only=True` 스트리밍 파서 도입 및 청크 단위 이터레이터 패턴 적용.
2. **수식(Formula) 보존 옵션**:
   - `data_only=False`와 `data_only=True`를 듀얼 로드하여 계산된 값과 원본 엑셀 수식(`=SUM(C2:C4)`)을 동시 보존하는 메타데이터 확장.
