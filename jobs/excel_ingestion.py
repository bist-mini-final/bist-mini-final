"""Declarative pipeline recipe for Excel spreadsheet ingestion and vector indexing."""

from __future__ import annotations

from .base import JobDefinition

EXCEL_INGESTION_JOB = JobDefinition(
    job_id="excel_ingestion",
    name="엑셀 스프레드시트 구조화 및 pgvector 인덱싱",
    description="비정형 재무제표 엑셀 파일을 Luna VLM으로 감지하고 3072차원 벡터 인덱스에 적재하는 파이프라인",
    queue_name="excel-ingestion",
    module_sequence=[
        "processed_file_selector",
        "luna_vlm_structure_detector",
        "cell_text_serializer",
        "cell_text_embedder",
        "pgvector_index_writer",
        "sheet_metadata_persistence",
        "company_entity_extractor",
    ],
)

__all__ = ["EXCEL_INGESTION_JOB"]
