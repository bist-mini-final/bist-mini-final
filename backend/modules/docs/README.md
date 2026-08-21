# Backend module guides

> 이 디렉터리의 문서는 등록된 `ModuleDefinition`과 Pydantic DTO에서 자동 생성됩니다. 개별 파일을 직접 수정하지 마세요.

## 확인 방법

- 읽기 중심 API 문서: [ReDoc](/redoc)
- 브라우저에서 직접 실행: [Swagger UI](/docs)
- 원본 OpenAPI 계약: [OpenAPI JSON](/openapi.json)
- 모듈별 실시간 Markdown: `/api/modules/{module_type}/docs`

## 문서 재생성

DTO, 포트 또는 `ModuleDefinition`을 변경한 뒤 프로젝트 루트에서 실행합니다.

```bash
python -m backend.tools.generate_module_docs
```

테스트는 체크인된 문서가 현재 코드 계약과 동일한지 검사합니다.

| Module | Category | Guide |
|---|---|---|
| `adaptive_query_decomposer` | Logic | [Adaptive Query Decomposer](./adaptive_query_decomposer.md) |
| `adaptive_rrf_fusion` | Logic | [Adaptive RRF Fusion](./adaptive_rrf_fusion.md) |
| `answer_cache_writer` | Output | [Answer Cache Writer](./answer_cache_writer.md) |
| `answer_refiner` | Output | [Direct Cell Answer Refiner](./answer_refiner.md) |
| `bfs_llm_structure_detector` | Logic | [BFS + LLM Table Structure Detector](./bfs_llm_structure_detector.md) |
| `bm25_retriever` | Logic | [BM25 Keyword Retriever](./bm25_retriever.md) |
| `cell_text_embedder` | Logic | [Cell Text Embedder](./cell_text_embedder.md) |
| `cell_text_serializer` | Transform | [Structured Cell Text Serializer](./cell_text_serializer.md) |
| `company_entity_extractor` | VLM Vision | [Company Entity Extractor](./company_entity_extractor.md) |
| `context` | Transform | [Context Expander](./context.md) |
| `dataframe_source` | Source | [DataFrame Source (Code RAG)](./dataframe_source.md) |
| `decomposer` | Logic | [LLM Query Decomposer](./decomposer.md) |
| `dense_retriever` | Logic | [Dense Vector Retriever](./dense_retriever.md) |
| `direct_query_decomposer` | Logic | [Direct Query Baseline](./direct_query_decomposer.md) |
| `docling_table_detector` | Logic | [Docling Table Region Detector](./docling_table_detector.md) |
| `embedder` | Logic | [Query Embedder](./embedder.md) |
| `exhaustive_cell_text_serializer` | Transform | [Exhaustive Cell Header Serializer](./exhaustive_cell_text_serializer.md) |
| `financial_formula_calculator` | Logic | [Financial Formula Calculator](./financial_formula_calculator.md) |
| `image_tile_source` | Source | [Image Tile Source (PixelRAG)](./image_tile_source.md) |
| `index_company_persistence` | Storage / DB | [Index Company Persistence](./index_company_persistence.md) |
| `json_inspector` | Output | [JSON Data Inspector](./json_inspector.md) |
| `json_transformer` | Transform | [JSON Format Mapper](./json_transformer.md) |
| `llm_query_router` | Logic | [LLM Query Router](./llm_query_router.md) |
| `local_vlm_structure_detector` | Logic | [Local VLM Table Structure Detector](./local_vlm_structure_detector.md) |
| `luna_vlm_structure_detector` | Logic | [Luna Full-Sheet Structure Detector](./luna_vlm_structure_detector.md) |
| `multi_company_collection_loader` | Storage | [Multi-Company Collection Loader](./multi_company_collection_loader.md) |
| `openpyxl_region_detector` | Logic | [OpenPyXL Table Region Classifier](./openpyxl_region_detector.md) |
| `pgvector_collection_loader` | Source | [PostgreSQL pgvector Collection Loader](./pgvector_collection_loader.md) |
| `pgvector_index_writer` | Transform | [PostgreSQL pgvector Writer](./pgvector_index_writer.md) |
| `pgvector_retriever` | Logic | [PostgreSQL pgvector Retriever](./pgvector_retriever.md) |
| `prebuilt_index_loader` | Source | [Pre-built Vector Index Loader](./prebuilt_index_loader.md) |
| `processed_file_selector` | Source | [Processed Excel File Selector](./processed_file_selector.md) |
| `qa_example_loader` | Source | [QA Example Bank Loader](./qa_example_loader.md) |
| `query_input` | Source | [Query Input & Search](./query_input.md) |
| `reader` | Output | [LLM Reader Answer](./reader.md) |
| `rrf_fusion` | Logic | [RRF Fusion](./rrf_fusion.md) |
| `semantic_query_matcher` | Logic | [Semantic Query Matcher](./semantic_query_matcher.md) |
| `semantic_scoped_dense_retriever` | Logic | [Semantic-Scoped Dense Retriever](./semantic_scoped_dense_retriever.md) |
| `semantic_scoped_pgvector_retriever` | Logic | [Semantic-Scoped pgvector Retriever](./semantic_scoped_pgvector_retriever.md) |
| `sheet_metadata_persistence` | Storage / DB | [Sheet Metadata Persistence](./sheet_metadata_persistence.md) |
| `template_query_decomposer` | Logic | [Template Query Decomposer](./template_query_decomposer.md) |
| `thesaurus_decomposer` | Logic | [Thesaurus Financial Decomposer](./thesaurus_decomposer.md) |
| `timeseries_context_expander` | Logic | [Time-Series Full-Row Context Expander](./timeseries_context_expander.md) |
| `vector_index_writer` | Transform | [Vector Index Writer](./vector_index_writer.md) |
