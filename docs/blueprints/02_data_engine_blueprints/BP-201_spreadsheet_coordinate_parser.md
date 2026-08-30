# [BP-201] Spreadsheet 2D 좌표 정규화와 직렬화
> **Document Code:** `BP-201` | **Category:** Data Engine Blueprint | **Status:** Implemented & Operational
> **Source Roots:** [`backend/storage/spreadsheets/`](file:///c:/Repos/bist-mini-final/backend/storage/spreadsheets/), [`modules/structure/`](file:///c:/Repos/bist-mini-final/modules/structure/)

---

## 1. 목적

재무 workbook의 값은 cell 하나만으로 의미가 완성되지 않습니다. 행 계정명, 열 기간, unit, 병합 header, sheet와 company scope를 보존해 검색 text와 source evidence를 함께 만들어야 합니다.

---

## 2. 정규화 규칙

1. workbook과 sheet의 원래 순서·이름을 보존합니다.
2. merged range의 anchor 값을 해당 header 문맥을 해석할 때 공유하되 원본 좌표는 바꾸지 않습니다.
3. cell은 row/column index와 Excel coordinate를 모두 가집니다.
4. formula cell은 값과 formula/source 표현을 혼동하지 않도록 명시적으로 처리합니다.
5. blank/hidden 영역의 포함 여부는 parser config와 source metadata로 남깁니다.
6. amount의 currency·scale·period를 가능한 한 명시적 metadata로 분리합니다.

---

## 3. `header_with_value` 검색 표현

```text
Company: {company} | Sheet: {sheet} | Row Header: {row_header_path} | Column Header: {column_header_path} | Cell Value: {display_value}
```

직렬화 text는 dense embedding과 keyword index가 같은 cell 의미를 공유하도록 합니다. `Company`는 `Row Header`에 섞지 않는 독립 필드이며, table `title` 영역의 회사명·출처·단위·기간 설명도 행 계정명 계층에 포함하지 않습니다. raw workbook 값, `cell_coord`, row/column index, unit과 source 정보는 별도 metadata에 남겨 reader와 BI가 evidence로 참조합니다.

`header_only` 변형의 `Cell Value: ?`는 검색 recall 보조용이며 사용자 답변의 근거가 될 수 없습니다. Context Expander는 같은 좌표의 `header_with_value`/실제 metadata 값을 우선 복원하고, Reader는 값이 없는 셀을 인용 후보에서 제외합니다.

---

## 4. 후속 검색 흐름

```mermaid
flowchart LR
    XLSX["workbook"] --> GRID["2D cell grid"]
    GRID --> STRUCTURE["validated table regions"]
    STRUCTURE --> SERIALIZE["cell_text_serializer"]
    SERIALIZE --> EMBED["cell_text_embedder"]
    EMBED --> INDEX["pgvector + keyword metadata"]
    INDEX --> RETRIEVE["dense/keyword + RRF"]
    RETRIEVE --> EXPAND["neighbor/header context"]
    EXPAND --> READER["answer + cited cells"]
```

구조 감지 실패 시 임의의 header heuristic으로 계속 적재하지 않습니다. 구조 감지와 좌표 정규화는 분리돼 있어 외부 vision 결과도 실제 workbook bounds와 대조합니다.

---

## 5. 무결성·성능 검증

- 병합 header, 다층 header, 음수·괄호 숫자, 단위 행, 여러 FY 열에 대한 fixture test를 유지합니다.
- serialized record에서 workbook/sheet/cell 좌표를 역추적할 수 있어야 합니다.
- batch size와 artifact 사용량은 데이터셋 benchmark로 조정하며 근거 없는 고정 절감률을 문서화하지 않습니다.
- large workbook parsing은 API 이벤트 루프가 아니라 worker thread/one-shot worker에서 실행합니다.
