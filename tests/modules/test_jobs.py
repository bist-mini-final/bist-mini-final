from __future__ import annotations

import unittest

from jobs import ALL_JOBS, BI_MATERIALIZATION_JOB, EXCEL_INGESTION_JOB, RAG_QUERY_JOB, get_job_definition
from modules.common.base_module import BaseModule


class JobsDefinitionTests(unittest.TestCase):
    def test_all_jobs_registered(self) -> None:
        self.assertEqual(len(ALL_JOBS), 3)
        self.assertEqual(get_job_definition("excel_ingestion"), EXCEL_INGESTION_JOB)
        self.assertEqual(get_job_definition("bi_materialization"), BI_MATERIALIZATION_JOB)
        self.assertEqual(get_job_definition("rag_query"), RAG_QUERY_JOB)

    def test_job_module_sequences_are_non_empty(self) -> None:
        for job in ALL_JOBS:
            self.assertGreater(len(job.module_sequence), 0)
            self.assertTrue(bool(job.name))
            self.assertTrue(bool(job.description))

    def test_invalid_job_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            get_job_definition("non_existent_job")
