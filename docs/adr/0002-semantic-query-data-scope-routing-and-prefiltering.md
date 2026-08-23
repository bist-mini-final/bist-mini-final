# ADR-002: 서브쿼리별 PostgreSQL Data Scope 라우팅

- **상태**: Accepted
- **최종 갱신**: 2026-08-23
- **영역**: Query decomposition, collection routing, pgvector/FTS pre-filtering

## 배경

여러 기업과 워크북을 하나의 PostgreSQL/pgvector 저장소에 색인하면 같은 시트명과
유사한 재무 항목이 반복된다. 전체 collection을 검색하거나 사용자가 검색 collection을
직접 선택하면 다음 문제가 생긴다.

- 서브쿼리마다 필요한 파일이 다른 복합 질문을 표현할 수 없다.
- 사용자가 collection topology와 embedding 계약을 알아야 한다.
- 모든 collection을 교차 검색해 불필요한 vector/FTS I/O가 증가한다.
- 서로 다른 embedding model 또는 dimension을 하나의 query vector로 검색할 수 없다.

## 결정

표준 RAG 흐름을 다음 하나로 고정한다.

```text
Query
  → Decomposer
  → PostgreSQL Data Scope Catalog
  → LLM Query Router
  → Retrieval Plan
      ├─ model/dimension grouped Query Embedder → Dense HNSW
      └─ routed collection Keyword GIN/FTS
  → RRF → Context Expander → Reader
```

1. `PgVectorDataScopeModule`은 collection metadata와 정규화된 `sheets` 테이블만 읽는다.
   embedding table을 count 또는 catalog 탐색 목적으로 스캔하지 않는다.
2. `DecomposerModule`은 collection을 모르는 상태에서 원자적 서브쿼리를 먼저 만든다.
3. `LlmQueryRouterModule`은 각 `subquery_index`에 catalog에 존재하는 `index_id`를
   하나 이상 지정한다. 존재하지 않는 ID, 누락된 서브쿼리, 선택 한도 초과는 실패다.
4. `RetrievalPlanDTO`가 서브쿼리, concrete collection, company/sheet,
   embedding model/dimension lineage의 단일 계약이다.
5. Query Embedder는 `(model, dimension)`별로 텍스트를 deduplicate/batch하고 결과를
   서브쿼리와 collection 쌍에 다시 대응시킨다.
6. Dense와 keyword retriever는 각 서브쿼리에 지정된 collection 밖을 검색하지 않는다.
7. company/sheet metadata predicate가 0건이면 같은 collection 안에서만 해당 predicate를
   제거한다. 다른 collection 또는 전체 DB로 완화하지 않는다.
8. 검색 후보는 `index_id`를 끝까지 보존하며 Context Expander도 후보별 collection에서만
   행 컨텍스트를 조회한다.

## DB 조회 계약

Data Scope catalog는 다음 projection만 조회한다.

```sql
SELECT
    collection.name,
    collection.cmetadata,
    ARRAY(
        SELECT sheet.sheet_name
        FROM sheets AS sheet
        WHERE sheet.file_id = collection.cmetadata->>'workbook_hash'
          AND sheet.is_visible = TRUE
        ORDER BY sheet.sheet_index, sheet.sheet_name
    )
FROM langchain_pg_collection AS collection
ORDER BY collection.name;
```

문서 수는 collection metadata의 ingestion 결과를 사용한다. 질의 라우팅을 위해
`langchain_pg_embedding` 전체를 집계하지 않는다.

## 거부한 대안

- **사용자 수동 collection 선택**: UI와 실행 계약에서 제거한다.
- **모든 collection 교차 검색**: I/O와 오염 가능성이 커서 허용하지 않는다.
- **Router를 Decomposer 앞에 배치**: 아직 존재하지 않는 서브쿼리에 collection을
  대응할 수 없으므로 허용하지 않는다.
- **한 개의 전역 query embedding model**: 저장된 collection 계약과 차원이 어긋날 수
  있으므로 허용하지 않는다.

## 결과

- 복합 질문 하나가 서브쿼리별로 서로 다른 collection을 정확히 사용할 수 있다.
- Playground와 BI handoff에서 collection 선택 상태가 사라진다.
- Router가 선택한 범위만 검색하므로 vector/FTS I/O가 제한된다.
- 다중 embedding model/dimension에서도 query vector lineage가 보장된다.
- 잘못된 Router 출력은 조용한 전역 검색이 아니라 명시적 계약 오류로 종료된다.
