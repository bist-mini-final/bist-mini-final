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
| `answer_cache_writer` | Output | [Answer Cache Writer](./answer_cache_writer.md) |
| `bfs_llm_structure_detector` | Logic | [BFS + LLM Table Structure Detector](./bfs_llm_structure_detector.md) |
| `bm25_retriever` | Logic | [BM25 Keyword Retriever](./bm25_retriever.md) |
| `cell_text_embedder` | Logic | [Cell Text Embedder](./cell_text_embedder.md) |
| `cell_text_serializer` | Transform | [Structured Cell Text Serializer](./cell_text_serializer.md) |
| `context` | Transform | [Context Expander](./context.md) |
| `dataframe_source` | Source | [DataFrame Source (Code RAG)](./dataframe_source.md) |
| `decomposer` | Logic | [LLM Query Decomposer](./decomposer.md) |
| `dense_retriever` | Logic | [Dense Vector Retriever](./dense_retriever.md) |
| `docling_table_detector` | Logic | [Docling Table Region Detector](./docling_table_detector.md) |
| `embedder` | Logic | [Query Embedder](./embedder.md) |
| `exhaustive_cell_text_serializer` | Transform | [Exhaustive Cell Header Serializer](./exhaustive_cell_text_serializer.md) |
| `image_tile_source` | Source | [Image Tile Source (PixelRAG)](./image_tile_source.md) |
| `json_inspector` | Output | [JSON Data Inspector](./json_inspector.md) |
| `json_transformer` | Transform | [JSON Format Mapper](./json_transformer.md) |
| `local_vlm_structure_detector` | Logic | [Local VLM Table Structure Detector](./local_vlm_structure_detector.md) |
| `luna_vlm_structure_detector` | Logic | [Luna Full-Sheet Structure Detector](./luna_vlm_structure_detector.md) |
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
| `vector_index_writer` | Transform | [Vector Index Writer](./vector_index_writer.md) |
