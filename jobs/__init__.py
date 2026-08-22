"""Declarative composable pipeline job recipes."""

from .base import JobDefinition
from .bi_materialization import BI_MATERIALIZATION_JOB
from .excel_ingestion import EXCEL_INGESTION_JOB
from .rag_pipeline import RAG_QUERY_JOB

ALL_JOBS = [
    EXCEL_INGESTION_JOB,
    BI_MATERIALIZATION_JOB,
    RAG_QUERY_JOB,
]

JOB_REGISTRY = {job.job_id: job for job in ALL_JOBS}


def get_job_definition(job_id: str) -> JobDefinition:
    try:
        return JOB_REGISTRY[job_id]
    except KeyError as error:
        raise KeyError(f"지원하지 않는 Job ID입니다: {job_id}") from error


__all__ = [
    "ALL_JOBS",
    "BI_MATERIALIZATION_JOB",
    "EXCEL_INGESTION_JOB",
    "JOB_REGISTRY",
    "JobDefinition",
    "RAG_QUERY_JOB",
    "get_job_definition",
]
