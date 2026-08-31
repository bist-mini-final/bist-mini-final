# [BP-303] Dense + Sparse + RRF 융합 & 셀 확장 회로
> **Document Code:** `BP-303` | **Category:** Retrieval & Fusion Blueprint | **Status:** Implemented & Operational
> **Source Files:** [`modules/retrieval/pgvector_retriever.py`](file:///c:/Repos/bist-mini-final/modules/retrieval/pgvector_retriever.py), [`modules/retrieval/postgres_native_keyword_retriever.py`](file:///c:/Repos/bist-mini-final/modules/retrieval/postgres_native_keyword_retriever.py), [`modules/retrieval/rrf_fusion.py`](file:///c:/Repos/bist-mini-final/modules/retrieval/rrf_fusion.py), [`modules/retrieval/context_expander.py`](file:///c:/Repos/bist-mini-final/modules/retrieval/context_expander.py)

---

## 1. 하이브리드 검색 및 융합 파이프라인 구조 (Hybrid Retrieval Flow)

재무 엑셀 데이터는 "영업이익", "당기순손익"과 같은 **정확한 용어 일치(Exact Term Match)**와 "작년 장사해서 번 돈", "회사 부채 규모"와 같은 **자연어 의미론적 질의(Semantic Query)**를 동시에 처리해야 합니다.

`bist-mini-final`은 pgvector Dense 벡터 검색과 PostgreSQL TSVector BM25 키워드 검색을 병렬 수행한 후 **RRF (Reciprocal Rank Fusion)**로 순위를 융합하고, 검색된 셀을 2D 테이블 문맥으로 확장합니다.

```mermaid
flowchart TD
    QUERY["사용자 질의 (User Financial Query)"] --> SCOPE["PgVectorDataScopeModule (기업/시트/연도 필터 생성)"]
    
    subgraph ParallelRetrieval ["병렬 검색 계층 (Parallel Retrieval Layer)"]
        SCOPE --> DENSE["1. PgVectorRetrieverModule<br>(3072d Cosine Similarity ANN)"]
        SCOPE --> SPARSE["2. PostgresNativeKeywordRetrieverModule<br>(TSVector BM25 Full-Text Search)"]
    end

    DENSE -->|Ranked Dense Candidates| RRF["3. RrfFusionModule<br>(Reciprocal Rank Fusion, k=60)"]
    SPARSE -->|Ranked Sparse Candidates| RRF
    
    RRF -->|Top-K Fused Candidates| EXPAND["4. PgContextExpanderModule<br>(2D 그리드 셀 좌표 기반 Row/Table 확장)"]
    EXPAND --> READER["ReaderModule (LLM 수식 검증 및 답변 생성)"]
```

---

## 2. RRF (Reciprocal Rank Fusion) 수학적 공식

$$
\text{RRF Score}(d) = \sum_{m \in \{\text{Dense}, \text{BM25}\}} \frac{1}{k + r_m(d)}
$$

- $d$: 평가 대상 엑셀 셀 청크 (Candidate Cell Chunk)
- $m$: 검색 모델 채널 (Dense pgvector 또는 Sparse PostgreSQL FTS)
- $r_m(d)$: 해당 검색 모델 $m$ 내에서의 순위 (1-indexed Rank)
- $k$: 랭킹 스무딩 상수 (**기본값: $60$**)

### RRF 결합 효과 예시
- **사례 1 (Dense 1위, Sparse 5위)**: $\frac{1}{60 + 1} + \frac{1}{60 + 5} = 0.01639 + 0.01538 = 0.03177$ -> **최상위 승격**
- **사례 2 (Dense 단독 1위, Sparse 미검색)**: $\frac{1}{60 + 1} + 0 = 0.01639$
- **사례 3 (양쪽 모두 1위)**: $\frac{1}{60+1} + \frac{1}{60+1} = 0.03278$ -> **절대적 1위 확정**

---

## 3. 기하학적 2D 셀 컨텍스트 확장 회로 (`PgContextExpanderModule`)

단일 셀($C5$) 하나만으로는 해당 수치가 매출액인지 감가상각비인지, 직전 연도 대비 증감률이 얼마인지 LLM이 파악할 수 없습니다. 따라서 RRF로 선별된 상위 좌표를 기준으로 **2D 영역(상위 계층 헤더, 시계열 비교 열, 인접 행)을 단일 표준 규격(`header_with_value`)으로 복원 및 확장**합니다.

```mermaid
graph TD
    TARGET["Retrieved Top-K Cell: samsung:포괄손익계산서:C15 (영업이익: 6,567,200)"]
    
    subgraph ContextExpansion ["2D Grid Context Expansion Engine"]
        HDR["1. 상위 열 헤더 복원 (제 55기, 2023.12)"]
        STUB["2. 좌측 행 계층 경로 복원 (영업수익 > 매출총이익 > 영업이익)"]
        NEIGHBOR["3. 인접 비교 연도 열 복원 (2022.12 제 54기)"]
        CANONICAL["4. 단일 표준 규격(header_with_value) 라인들로 합성 (BP-201 일치)"]
    end

    TARGET --> ContextExpansion
    ContextExpansion --> RESULT["Canonical Structured Context Block for LLM Prompt"]
```

### [BP-201 표준 일치] 생성된 확장 컨텍스트 블록 예시 (Canonical Context Block)

```text
[Context Block: Top-K 융합 및 2D 이웃 확장 셀 목록]
Company: 삼성전자 | Sheet: 포괄손익계산서(연결) | Row Header: 영업수익 > 매출액 | Column Header: 2022.12 (제 54기) | Cell Value: 302,231,360
Company: 삼성전자 | Sheet: 포괄손익계산서(연결) | Row Header: 영업수익 > 매출액 | Column Header: 2023.12 (제 55기) | Cell Value: 258,935,494
Company: 삼성전자 | Sheet: 포괄손익계산서(연결) | Row Header: 영업수익 > 매출총이익 > 영업이익 | Column Header: 2022.12 (제 54기) | Cell Value: 43,370,290
Company: 삼성전자 | Sheet: 포괄손익계산서(연결) | Row Header: 영업수익 > 매출총이익 > 영업이익 | Column Header: 2023.12 (제 55기) | Cell Value: 6,567,200
```

* **표현 일관성과 파편화 방지**: 마크다운 표를 다시 조립하기보다 [BP-201]의 `header_with_value`와 원본 좌표 metadata를 유지해 dense/keyword/reader가 같은 cell 의미를 공유합니다. 토큰·정확도 효과는 benchmark에서 별도로 측정합니다.
* **검색/Reader 경계 규칙**: `Cell Value: ?`는 값 미지정을 뜻하는 검색 와일드카드입니다. Query Decomposer가 만든 이 표기는 Query Embedder와 Dense 유사도 검색까지 그대로 유지하며, 검색 후보 좌표와 2D 확장에도 사용할 수 있습니다. 단, Reader 입력 경계에서는 `Cell Value`가 실제 값인 셀만 통과시킵니다. Reader의 `[Context Blocks]`, 검증 가능한 근거 목록, `lookup_cell_metadata` 도구 결과는 모두 이 공통 필터를 거쳐 재구성되며 `?`, `NA`, `N/A`, `NM`, `#PEND`는 모델에 전달하지 않습니다.

---

## 4. 범위와 구현 결정

1. **Cross-Encoder Re-ranker — 범위 제외 (Out of Scope)**:
   - 검색 순위는 pgvector Dense 검색, BM25 Sparse 검색, RRF 융합의 현재 경로를 기준선으로 유지한다.
   - `bge-reranker-large`, Cohere Re-rank 등 별도 재순위 모델의 추가·운영은 이 프로젝트의 구현 범위에 포함하지 않는다.
2. **구현됨 — 명시적 bounded row expansion**:
   - 기본은 검색된 단일 행의 실제 값 셀을 복원하고 `adjacent_radius`를 지정한 경우에만 최대 20행 반경으로 확장합니다. 문서에 과거 기재된 고정 $\pm 3$행 동작은 현재 계약이 아닙니다.
   - 현재 persisted cell metadata에는 versioned `table_id`와 `data_range`가 없으므로 런타임이 Luna 범위를 추정해 임의로 잘라내지 않습니다. adaptive table window가 필요해지면 serializer metadata schema, 기존 collection 재적재, retrieval contract를 함께 버전 변경합니다.
3. **구현됨 — 비동기 검색 및 2D 컨텍스트 확장**:
   - Dense와 keyword 검색은 `AsyncConnectionPool`을 사용하고 동일 배치에서 `TaskGroup`으로 병렬 실행합니다.
   - Context Expander는 검색 후보를 컬렉션·시트별 행 집합으로 묶어 `fetch_rows_cells_async()`를 병렬 호출합니다. 동기·비동기 경로는 동일한 정규화·중복 제거·출력 렌더러를 공유합니다.
   - Reader의 `lookup_cell_metadata` 도구도 LangChain `ainvoke()`에서 `fetch_cells_by_metadata_async()`를 직접 await하므로 도구 반복 중 이벤트 루프를 차단하지 않습니다.
