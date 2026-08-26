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
   - 병합 영역 `A1:C1`에 "재무상태표 (2023)" 값이 있을 때, 실제 데이터 추출 시 `A1`, `B1`, `C1` 전체에 부모 헤더 문맥을 전파합니다.
2. **2D 직교 좌표계 표준화**:
   - `Row Index` (1-indexed 정수)
   - `Column Letter / Index` (예: `A` -> `1`, `AA` -> `27`)
   - `Sheet Code` 매핑: `손익계산서` -> `IS`, `재무상태표` -> `BS`, `현금흐름표` -> `CF`

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

## 4. 직렬화 변형 모드 (Serializer Variant Modes)

| 모드명 | 직렬화 형식 | 목적 및 임베딩 최적화 |
| :--- | :--- | :--- |
| `header_with_value` | `Company: ... \| Sheet: ... \| Row: ... \| Col: ... \| Value: ...` | **[기본값]** pgvector Dense 벡터 검색 및 수치 질의 매칭 |
| `row_block_markdown` | `\| 계정과목 \| 2022 \| 2023 \|\n\| 영업이익 \| 43370 \| 65670 \|` | LLM Context Expander용 마크다운 표 표현 |
| `hierarchical_key_value`| `삼성전자.손익계산서.영업이익[2023] = 65670` | 정밀 시맨틱 키워드 FTS 검색 매칭 |

---

## 5. 리팩토링 타깃 (Refactoring Targets)

1. **대용량 시트 메모리 최적화**:
   - As-Is: OpenPyXL 전체 메모리 로드 (`load_workbook(data_only=True)`). 100MB 이상 엑셀에서 메모리 스파이크 발생 가능.
   - To-Be: `read_only=True` 스트리밍 파서 도입 및 청크 단위 이터레이터 패턴 적용.
2. **수식(Formula) 보존 옵션**:
   - `data_only=False`와 `data_only=True`를 듀얼 로드하여 계산된 값과 원본 엑셀 수식(`=SUM(C2:C4)`)을 동시 보존하는 메타데이터 확장.
