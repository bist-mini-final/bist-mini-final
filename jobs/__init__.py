"""Declarative composable pipeline job recipes."""

from .base import (
    BaseJobDefinition,
    DagJobDefinition,
    JobDefinition,
    JobEdge,
    JobNode,
    KubernetesWorkerPolicy,
    WorkerJobDefinition,
)
from .benchmark import BENCHMARK_JOB
from .bi_materialization import (
    BI_MATERIALIZATION_JOB,
    BI_METRIC_EXTRACTION_JOB,
    BI_QUESTION_JOB,
)
from .excel_ingestion import EXCEL_INGESTION_JOB
from .rag_pipeline import RAG_QUERY_JOB

ALL_JOBS = [
    EXCEL_INGESTION_JOB,
    BI_MATERIALIZATION_JOB,
    BI_QUESTION_JOB,
    BI_METRIC_EXTRACTION_JOB,
    BENCHMARK_JOB,
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
    "BaseJobDefinition",
    "BENCHMARK_JOB",
    "BI_MATERIALIZATION_JOB",
    "BI_METRIC_EXTRACTION_JOB",
    "BI_QUESTION_JOB",
    "EXCEL_INGESTION_JOB",
    "JOB_REGISTRY",
    "DagJobDefinition",
    "JobDefinition",
    "JobEdge",
    "JobNode",
    "KubernetesWorkerPolicy",
    "RAG_QUERY_JOB",
    "WorkerJobDefinition",
    "get_job_definition",
]
