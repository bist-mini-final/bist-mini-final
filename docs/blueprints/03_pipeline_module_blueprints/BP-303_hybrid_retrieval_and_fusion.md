# [BP-303] Dense + Sparse + RRF 융합 & 셀 확장 회로
> **Document Code:** `BP-303` | **Contract State:** Target Architecture | **Capability State:** Operational | **Structure State:** Complete
> **Target Ownership:** `modules/retrieval`, `backend/domains/data_sources/application`, `backend/domains/data_sources/infrastructure/pgvector`, `backend/platform/pgvector`
> **Current References:** [`modules/retrieval/pgvector_retriever.py`](../../../modules/retrieval/pgvector_retriever.py), [`modules/retrieval/postgres_native_keyword_retriever.py`](../../../modules/retrieval/postgres_native_keyword_retriever.py), [`modules/retrieval/rrf_fusion.py`](../../../modules/retrieval/rrf_fusion.py), [`modules/retrieval/context_expander.py`](../../../modules/retrieval/context_expander.py), [`modules/reader/reader.py`](../../../modules/reader/reader.py), [`backend/shared/application/cell_evidence.py`](../../../backend/shared/application/cell_evidence.py)

---

## 1. 하이브리드 검색 및 융합 파이프라인 구조 (Hybrid Retrieval Flow)

재무 엑셀 데이터는 "영업이익", "당기순손익"과 같은 **정확한 용어 일치(Exact Term Match)**와 "작년 장사해서 번 돈", "회사 부채 규모"와 같은 **자연어 의미론적 질의(Semantic Query)**를 동시에 처리해야 합니다.

`bist-mini-final`은 pgvector Dense 벡터 검색과 PostgreSQL FTS 키워드 검색을 병렬 수행한 후 **RRF (Reciprocal Rank Fusion)**로 순위를 융합하고, 검색된 셀을 행 단위 문맥으로 확장합니다. 현재 키워드 SQL은 `to_tsvector('simple', ...)`, `plainto_tsquery`와 `ts_rank_cd`를 사용합니다. BM25 실험과 현재 FTS 구현은 구분합니다. [실제 검색 SQL](../../../backend/domains/data_sources/infrastructure/pgvector/retrieval.py)

```mermaid
flowchart TD
    QUERY["QueryInputModule<br>(query_context)"] --> DECOMPOSE["Scope-aware DecomposerModule<br>(원자 질의 + collection 결합)"]
    CATALOG["PgVectorDataScopeModule<br>(collection/company/ticker/sheet catalog)"] --> DECOMPOSE
    DECOMPOSE -->|RetrievalPlanDTO| EMBED["Query Embedder"]

    subgraph ParallelRetrieval ["병렬 검색 계층 (Parallel Retrieval Layer)"]
        EMBED --> DENSE["1. PgVectorRetrieverModule<br>(collection embedding 계약별 ANN)"]
        DECOMPOSE --> SPARSE["2. PostgresNativeKeywordRetrieverModule<br>(TSVector Full-Text Search)"]
    end

    DENSE -->|Ranked Dense Candidates| RRF["3. RrfFusionModule<br>(Reciprocal Rank Fusion, k=60)"]
    SPARSE -->|Ranked Sparse Candidates| RRF

    RRF -->|Top-K Fused Candidates| EXPAND["4. PgContextExpanderModule<br>(같은 행·설정된 인접 행 확장)"]
    EXPAND --> READER["ReaderModule (실제 값·셀 근거 기반 답변 생성)"]
```

Decomposer의 두 입력 단자는 플레이그라운드에서도 독립 edge로 보입니다. `PgVectorDataScopeModule`은 DB에서 catalog만 읽는 Source 모듈이고, Decomposer는 한 번의 구조화 LLM 호출로 질문 분해와 data scope 결합을 함께 수행합니다. 출력의 모든 `index_id`는 catalog membership 검증을 통과해야 하며 회사명과 시트명은 실제 저장 표기로 정규화됩니다. 따라서 존재하지 않는 기업을 먼저 분해한 뒤 다른 collection으로 우회하는 경로는 허용하지 않습니다. Chatbot의 첨부+RAG 혼합 실행만 Query Context의 `external_context_sources`를 채울 수 있습니다. 이 경우 catalog 밖 기업은 attachment-owned 이름으로 기록하고 retrieval item을 만들지 않으며, catalog에 존재하는 기업의 route만 계속 실행합니다. 이 예외는 collection access를 넓히지 않고 첨부가 없는 실행에는 적용되지 않습니다. 서버가 정확히 하나의 catalog 기업으로 해석한 selection에서 모델이 반환한 ID가 전부 미등록이면 해당 기업의 scope로만 복구하고 `repaired_scope_count`를 남깁니다. 알려진 ID와 미등록 ID가 섞였거나 기업명이 catalog에 없거나 여러 기업으로 모호하면 계속 fail-closed 처리합니다. 반대로 모델이 catalog에 실제 존재하는 기업을 `unresolved_companies`에도 중복 표기한 false negative는 서버 catalog 해석을 우선합니다. 빈 item 응답이면서 실제 미등록 기업이 없는 경우에만 한 번 재분해하며 두 시도의 토큰·비용·지연과 `decomposition_attempts`를 합산합니다.

추정·전망·미래 마진/EPS 질문은 선택 기업에 `Key_Stats`가 존재하면 그 시트를 우선하고, 역사적 실적은 명시적으로 Key Stats를 요청하지 않는 한 각 재무제표 시트에 둡니다. 비교·추세·비율·회계 항등식은 모든 피연산 지표·기간을 원자 item으로 분해하며 필요한 최소 시트만 선택합니다. `세 회사` 같은 집합 표현은 현재 질문에 구성 기업이 명시되지 않으면 catalog 전체로 임의 확장하지 않습니다.

이 회로는 자유 질의와 BI exact lookup miss의 공통 fallback입니다. BI의 versioned metric catalog처럼 이미 지표·기간이 구조화된 요청은 BP-403의 metadata exact-evidence 조회를 먼저 실행합니다. 정확 값 셀이 있으면 불필요한 Decomposer·embedding·RRF 호출을 생략하고, 없을 때만 이 하이브리드 회로로 내려옵니다. BI 별칭·FY/LTM 판단은 BI bounded context가 소유하며 범용 retrieval module에 하드코딩하지 않습니다.

---

## 2. RRF (Reciprocal Rank Fusion) 수학적 공식

$$
\text{RRF Score}(d) = \sum_{m \in \{\text{Dense}, \text{FTS}\}} \frac{1}{k + r_m(d)}
$$

- $d$: 평가 대상 엑셀 셀 청크 (Candidate Cell Chunk)
- $m$: 검색 모델 채널 (Dense pgvector 또는 Sparse PostgreSQL FTS)
- $r_m(d)$: 해당 검색 모델 $m$ 내에서의 순위 (1-indexed Rank)
- $k$: 랭킹 스무딩 상수 (**기본값: $60$**)

### RRF 결합 효과 예시

- **사례 1 (Dense 1위, Sparse 5위)**: $\frac{1}{60 + 1} + \frac{1}{60 + 5} \approx 0.03178$ → **사례 2보다 높은 통합 점수**
- **사례 2 (Dense 단독 1위, Sparse 미검색)**: $\frac{1}{60 + 1} + 0 \approx 0.01639$
- **사례 3 (양쪽 모두 1위)**: $\frac{1}{60+1} + \frac{1}{60+1} \approx 0.03279$ → **이 두 채널 예시에서 가장 높은 점수**

한 채널에 없는 후보의 해당 채널 기여도는 0입니다. 최종 순위는 동일한 채널 구성에서 모든 후보의 합산 점수를 비교해 결정하며, 단일 사례만으로 항상 1위가 된다고 일반화하지 않습니다.

---

## 3. 기하학적 2D 셀 컨텍스트 확장 회로 (`PgContextExpanderModule`)

단일 셀($C5$) 하나만으로는 해당 수치가 매출액인지 감가상각비인지, 직전 연도 대비 증감률이 얼마인지 LLM이 파악할 수 없습니다. 따라서 RRF로 선별된 상위 좌표를 기준으로 **2D 영역(상위 계층 헤더, 시계열 비교 열, 인접 행)을 단일 표준 규격(`header_with_value`)으로 복원 및 확장**합니다.

```mermaid
graph TD
    TARGET["Retrieved Top-K Cell: C15<br/>Company: 삼성전자 · Sheet: 포괄손익계산서(연결)"]

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
* **Reader 근거 선택 규칙**: 값이 있는 Reader 후보 전체가 사용자 근거가 되는 것은 아닙니다. 각 후보에 서버가 `EVIDENCE-nnn` ID를 부여하고 LLM은 strict JSON Schema에 맞춰 `answer_markdown`과 실제 사용한 최소 `evidence_ids`만 반환합니다. backend는 ID를 전체 후보 allowlist와 대조한 뒤 완전한 `CellEvidenceDTO[]`로 투영합니다. 비교·추세·비율·증감·차이·회계 항등식은 결과뿐 아니라 각 원본값을 답변하고 모든 피연산 셀 ID를 선택해야 하며, 실제와 추정 기간을 명시적으로 구분합니다. 본문은 생성했으나 allowlist의 유효 ID를 하나도 선택하지 않은 경우에만 원 질문과 전체 후보를 그대로 둔 구조화 선택을 한 번 재시도합니다. 기간 기준 압축, 검색 상위 셀 자동 첨부, 서버측 근거 추측은 하지 않으며 재시도에도 유효 ID가 없으면 답변을 차단합니다. 첨부+RAG 2단계 질의에서는 첫 Reader의 책임을 적재 원천 부분 답변으로 명시하되 원 질문과 검색된 전체 실제 값 후보는 그대로 유지합니다. 본문에는 시트·좌표 문자열이나 `근거` section을 합성하지 않습니다.

---

## 4. 범위와 구현 결정

1. **구현됨 — 명시적 bounded row expansion**:
   - 기본은 검색된 단일 행의 실제 값 셀을 복원하고 `adjacent_radius`를 지정한 경우에만 최대 20행 반경으로 확장합니다. 문서에 과거 기재된 고정 $\pm 3$행 동작은 현재 계약이 아닙니다.
   - 현재 persisted cell metadata에는 versioned `table_id`와 `data_range`가 없으므로 런타임이 표 범위를 추정해 임의로 잘라내지 않습니다. adaptive table window가 필요해지면 serializer metadata schema, 기존 collection 재적재, retrieval contract를 함께 버전 변경합니다.
2. **구현됨 — 비동기 검색 및 2D 컨텍스트 확장**:
   - Dense와 keyword 검색은 `AsyncConnectionPool`을 사용하고 동일 배치에서 `TaskGroup`으로 병렬 실행합니다.
   - Context Expander는 검색 후보를 컬렉션·시트별 행 집합으로 묶어 `fetch_rows_cells_async()`를 병렬 호출합니다. 동기·비동기 경로는 동일한 정규화·중복 제거·출력 렌더러를 공유합니다.
   - Reader의 `lookup_cell_metadata` 도구도 LangChain `ainvoke()`에서 `fetch_cells_by_metadata_async()`를 직접 await하므로 도구 반복 중 이벤트 루프를 차단하지 않습니다.

---

## 5. 책임 분리와 구조 완료 조건

- query normalization, candidate와 evidence DTO, 실제 값만 Reader로 전달하는 정책은 data sources application contract로 둡니다.
- Dense/keyword SQL과 cell expansion mapping은 `data_sources/infrastructure/pgvector`, 범용 vector connection·codec은 `platform/pgvector`가 소유합니다.
- retrieval module은 각 capability port를 호출하고 RRF처럼 순수한 결합 알고리즘은 module 내부에서 provider 독립적으로 유지합니다.
- `Cell Value: ?` 후보는 retrieval recall에는 남기되 Reader input projection에서는 값 존재 여부를 공통 정책으로 강제합니다.
- module의 legacy storage facade import는 제거됐고 Dense/keyword/context expansion은 data-source retrieval port를 통해 같은 sync/async 정규화 계약을 사용합니다.
- 검색 기준선은 Dense + PostgreSQL keyword + RRF(`k=60`) + 2D context expansion입니다.
- 구조화 BI metric 요청의 기준선은 catalog exact-evidence first, 본 문서의 하이브리드 검색 second입니다. exact 조회도 collection/workbook/file lineage와 실제 값 필터를 동일하게 강제합니다.
- 검색 recall 단계의 `?`와 Reader evidence 단계의 실제 값 필터는 서로 다른 의도적 계약입니다. 어느 한쪽을 바꾸면 BP-201·BP-404와 검색/근거 회귀 테스트를 함께 갱신합니다.
