"""Declarative pipeline recipe for Excel spreadsheet ingestion and vector indexing."""

from __future__ import annotations

from .base import DagJobDefinition, JobEdge, JobNode

EXCEL_INGESTION_JOB = DagJobDefinition(
    job_id="excel_ingestion",
    name="엑셀 스프레드시트 구조화 및 pgvector 인덱싱",
    description=(
        "비정형 재무제표 엑셀 파일을 Luna VLM으로 감지하고 dense/FTS "
        "인덱스 및 시트·기업 메타데이터를 영속화합니다."
    ),
    queue_name="workflow-core",
    version="2",
    nodes=(
        JobNode("source", "processed_file_selector"),
        JobNode("structure", "luna_vlm_structure_detector"),
        JobNode("serialize", "cell_text_serializer"),
        JobNode("embed", "cell_text_embedder"),
        JobNode("write-index", "pgvector_index_writer"),
        JobNode("persist-sheets", "sheet_metadata_persistence"),
        JobNode("persist-company", "company_entity_extractor"),
    ),
    edges=(
        JobEdge("source-structure", "source", "structure", "output", "input"),
        JobEdge("structure-serialize", "structure", "serialize", "output", "input"),
        JobEdge("serialize-embed", "serialize", "embed", "output", "input"),
        JobEdge("embed-write", "embed", "write-index", "output", "input"),
        JobEdge(
            "structure-sheets",
            "structure",
            "persist-sheets",
            "output",
            "structure_input",
        ),
        JobEdge(
            "index-sheets",
            "write-index",
            "persist-sheets",
            "index_output",
            "index_input",
        ),
        JobEdge(
            "index-company",
            "write-index",
            "persist-company",
            "index_output",
            "index_input",
        ),
    ),
)

__all__ = ["EXCEL_INGESTION_JOB"]
