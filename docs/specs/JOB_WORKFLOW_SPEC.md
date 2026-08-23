# 표준 Job 및 DAG 명세

`jobs/`는 노드 순서 목록이 아니라 실행 가능한 포트 기반 DAG를 정의한다. 각 엣지는 `source_output`과 `target_input`을 명시해야 하며 backend는 이를 Workflow 문서로 투영한다.

## `excel_ingestion`

큐: `workflow-core`

```text
processed_file_selector ──> luna_vlm_structure_detector ──> cell_text_serializer
                                                           └─> cell_text_embedder
                                                               └─> pgvector_index_writer
luna_vlm_structure_detector.output ──────────────────────────> sheet_metadata_persistence.structure_input
pgvector_index_writer.index_output ──────────────────────────> sheet_metadata_persistence.index_input
pgvector_index_writer.index_output ──────────────────────────> company_entity_extractor.index_input
```

입력은 selector의 `file_name`과 선택적 sheet 목록이다. 완료 결과는 index ID, sheet metadata, company extraction summary이며 대형 cell/embedding 배열은 API 응답에 포함하지 않는다.

## `rag_query`

큐: `workflow-core`

```text
query_input ──> decomposer ──subqueries───────────┐
pgvector_data_scope ──scope_catalog───────────────┼─> llm_query_router
llm_query_router.retrieval_plan ──────────────────┼─> embedder
                                                  └─> keyword
embedder.routed_embeddings ─────────────────────────> dense
dense.dense_result + keyword.bm25_result ──────────> rrf_fusion
rrf_fusion.retrieval_json ─────────────────────────> pg_context_expander
pg_context_expander.context_json ──────────────────> reader
```

사용자는 collection을 선택하지 않는다. data scope 모듈은 DB의 compact collection/company/sheet/model/dimension catalog만 읽고, Router가 각 서브쿼리에 concrete collection을 지정한다. Query Embedder는 routing plan을 model/dimension별로 묶어 중복 호출 없이 임베딩하고, dense와 keyword 검색은 지정받은 collection 밖을 검색하지 않는다. metadata 조건이 0건이면 같은 collection 안에서만 company/sheet 조건을 완화한다.

## `bi_materialization` / `bi_question`

큐: `bi-materialization` → `bi-question`

API는 `bi_materialization_jobs`에 요청만 등록한다. `bi-materialization` ScaledJob이 문서 프로파일링과 질문 work item 생성을 수행하고, `bi-question` ScaledJob들이 표준 하이브리드 RAG 검색 → 계산/단위 정규화 → 근거 검증을 병렬 수행한다. 마지막 질문 worker가 PostgreSQL snapshot을 원자적으로 publish한다. 두 worker는 heartbeat를 갱신하며 stale claim만 새 generation으로 회수한다.

기업 catalog는 `langchain_pg_collection.cmetadata`의 `company_name`, `file_name`,
`workbook_hash`, collection `name`을 source lineage로 사용한다. 같은 기업의 collection이
여러 개면 최신 `created_at` source를 선택하되 게시된 BI company ID와 snapshot pointer는
유지한다. dashboard read는 current snapshot을 재사용하고 source-only 기업의 최초 요청만
멱등 materialization을 제출한다. 진행 상태는 API 계산이 아니라 PostgreSQL job/question
projection을 공통 SSE observer로 fan-out한다.

## `benchmark`

큐: `benchmark` → `workflow-core`

API는 `benchmark_jobs`에 비교 요청만 등록한다. 전용 benchmark ScaledJob이 각 case/workflow 조합의 run을 `workflow-core`에 제출하고 compact summary를 관찰한 뒤 채점한다. 완료된 비교 row와 active run ID를 매 단계 PostgreSQL에 저장하므로 coordinator Pod가 재시작되어도 완료 항목을 건너뛰고 진행 중 run부터 재개한다.

## DAG 유효성 완료 조건

- module type이 registry에 존재한다.
- 모든 edge의 source/target node가 존재한다.
- source output과 target input이 module definition에 존재하고 schema가 호환된다.
- 그래프가 비순환이며 모든 필수 입력이 runtime input 또는 upstream edge로 공급된다.
- worker task policy가 활성화되어 있고 timeout/retry가 직렬화 가능하다.
- terminal 상태에서 성공한 sink node가 하나 이상 존재한다.
