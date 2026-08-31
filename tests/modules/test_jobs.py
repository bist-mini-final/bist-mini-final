from __future__ import annotations

import unittest

from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.domain.models import WorkflowExecutionRequest
from backend.domains.workflow.infrastructure.job_catalog import workflow_from_job
from backend.domains.workflow.infrastructure.persistence import ResultCache, RunStore
from backend.storage.data_sources.ingestion_jobs import (
    IngestionJobService,
    IngestionRequest,
)
from jobs import (
    ALL_JOBS,
    BENCHMARK_JOB,
    BI_MATERIALIZATION_JOB,
    BI_METRIC_EXTRACTION_JOB,
    BI_QUESTION_JOB,
    EXCEL_INGESTION_JOB,
    INGESTION_EMBEDDING_SHARD_JOB,
    INGESTION_VECTOR_SHARD_JOB,
    RAG_QUERY_JOB,
    DagJobDefinition,
    WorkerJobDefinition,
    get_job_definition,
)
from tests.modules.registry_factory import create_test_registry


class JobsDefinitionTests(unittest.TestCase):
    def test_all_jobs_registered(self) -> None:
        self.assertEqual(len(ALL_JOBS), 8)
        self.assertEqual(get_job_definition("excel_ingestion"), EXCEL_INGESTION_JOB)
        self.assertEqual(get_job_definition("bi_materialization"), BI_MATERIALIZATION_JOB)
        self.assertEqual(get_job_definition("bi_question"), BI_QUESTION_JOB)
        self.assertEqual(get_job_definition("bi_metric_extraction"), BI_METRIC_EXTRACTION_JOB)
        self.assertEqual(get_job_definition("benchmark"), BENCHMARK_JOB)
        self.assertEqual(get_job_definition("rag_query"), RAG_QUERY_JOB)
        self.assertEqual(
            get_job_definition("ingestion_embedding_shard"),
            INGESTION_EMBEDDING_SHARD_JOB,
        )
        self.assertEqual(
            get_job_definition("ingestion_vector_shard"),
            INGESTION_VECTOR_SHARD_JOB,
        )

    def test_jobs_define_a_dag_or_worker_entrypoint(self) -> None:
        for job in ALL_JOBS:
            self.assertIsInstance(job, (DagJobDefinition, WorkerJobDefinition))
            if isinstance(job, DagJobDefinition):
                self.assertTrue(job.nodes)
            else:
                self.assertTrue(job.worker_entrypoint)
                self.assertTrue(job.worker_kind)
            self.assertTrue(bool(job.name))
            self.assertTrue(bool(job.description))

    def test_workflow_jobs_compile_against_live_module_ports(self) -> None:
        executor = WorkflowExecutor(create_test_registry(), RunStore(), ResultCache())
        for job in (EXCEL_INGESTION_JOB, RAG_QUERY_JOB, BI_METRIC_EXTRACTION_JOB):
            workflow = workflow_from_job(job)
            batches = executor.validate_graph(workflow.graph)
            self.assertGreater(len(batches), 0)
            self.assertEqual(
                {node.node_id for node in job.nodes},
                {node_id for batch in batches for node_id in batch},
            )

    def test_rag_query_embedder_accepts_the_router_retrieval_plan(self) -> None:
        executor = WorkflowExecutor(create_test_registry(), RunStore(), ResultCache())
        run = executor.create_run(
            workflow_from_job(RAG_QUERY_JOB),
            WorkflowExecutionRequest(),
        )
        run.nodes["route"].status = "succeeded"
        run.nodes["route"].output = {
            "query_context": {
                "question_id": "QUERY-TEST",
                "question_text": "FY2025 Revenue?",
            },
            "routes": [
                {
                    "subquery_index": 0,
                    "subquery": {"row_header": "Revenue"},
                    "collections": [
                        {
                            "index_id": "idx-test",
                            "file_name": "sample.xlsx",
                            "workbook_hash": "hash",
                            "company_name": "Example Corp",
                            "sheet_names": ["Financials"],
                            "model": "text-embedding-3-small",
                            "dimension": 1536,
                            "document_count": 1,
                        }
                    ],
                }
            ],
            "metrics": {},
        }
        embed_node = next(node for node in run.graph.nodes if node.id == "embed-query")

        should_execute, reason = executor._should_execute_node(run, embed_node)
        payload = executor._assemble_input(run, embed_node)

        self.assertTrue(should_execute, reason)
        self.assertEqual(
            payload["retrieval_plan"]["routes"][0]["collections"][0]["dimension"],
            1536,
        )
        executor.module_registry.get("embedder").input_model.model_validate(payload)

    def test_rag_query_uses_automatic_data_scope_routing(self) -> None:
        node_types = {node.node_id: node.module_type for node in RAG_QUERY_JOB.nodes}
        router_inputs = {
            (edge.source, edge.target_input)
            for edge in RAG_QUERY_JOB.edges
            if edge.target == "route"
        }

        self.assertEqual(node_types["data-scope"], "pgvector_data_scope")
        self.assertEqual(
            router_inputs,
            {
                ("decompose", "query_input"),
                ("data-scope", "scope_catalog"),
            },
        )
        self.assertEqual(
            {
                node.node_id: node.values
                for node in RAG_QUERY_JOB.nodes
                if node.node_id in {"data-scope", "route"}
            },
            {"data-scope": {}, "route": {}},
        )

    def test_ingestion_typed_object_edge_supplies_structure_input(self) -> None:
        executor = WorkflowExecutor(create_test_registry(), RunStore(), ResultCache())
        run = executor.create_run(
            workflow_from_job(EXCEL_INGESTION_JOB),
            WorkflowExecutionRequest(),
        )
        run.nodes["source"].status = "succeeded"
        run.nodes["source"].output = {
            "file_name": "sample.xlsx",
            "workbook_hash": "a" * 64,
            "sheet_names": ["Financials"],
        }
        structure_node = next(
            node for node in run.graph.nodes if node.id == "structure"
        )

        should_execute, reason = executor._should_execute_node(run, structure_node)
        payload = executor._assemble_input(run, structure_node)

        self.assertTrue(should_execute, reason)
        self.assertEqual(payload["file_name"], "sample.xlsx")
        executor.module_registry.get(
            "luna_vlm_structure_detector"
        ).input_model.model_validate(payload)

    def test_invalid_job_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            get_job_definition("non_existent_job")

    def test_new_ingestion_runs_use_only_the_canonical_workflow_id(self) -> None:
        request = IngestionRequest(file_name="sample.xlsx")
        self.assertEqual(
            IngestionJobService.workflow_id_for(request),
            "excel_ingestion",
        )

    def test_partial_claimed_run_remains_running_between_nodes(self) -> None:
        executor = WorkflowExecutor(create_test_registry(), RunStore(), ResultCache())
        run = executor.create_run(
            workflow_from_job(RAG_QUERY_JOB),
            WorkflowExecutionRequest(),
        )
        run.status = "running"
        run.nodes["query"].status = "succeeded"

        executor._refresh_run_status(run)

        self.assertEqual(run.status, "running")

    def test_resume_resets_failed_parallel_siblings_and_descendants(self) -> None:
        run_store = RunStore()
        executor = WorkflowExecutor(create_test_registry(), run_store, ResultCache())
        run = executor.create_run(
            workflow_from_job(RAG_QUERY_JOB),
            WorkflowExecutionRequest(),
        )

        for node_id in ("query", "data-scope", "route", "decompose"):
            run.nodes[node_id].status = "succeeded"
            run.nodes[node_id].output = {"preserved": node_id}
        run.nodes["keyword"].status = "failed"
        run.nodes["keyword"].error = "temporary PostgreSQL failure"
        for node_id in ("embed-query", "dense", "fuse", "expand-context", "read"):
            state = run.nodes[node_id]
            state.status = "skipped"
            state.skip_reason = "upstream batch failed"
            state.output = {"stale": node_id}
            state.cost_usd = 1.0
        executor._refresh_run_status(run)
        run_store.save(run)

        resumed = executor.prepare_resume(run.id)

        self.assertEqual(resumed.status, "queued")
        for node_id in ("query", "data-scope", "route", "decompose"):
            self.assertEqual(resumed.nodes[node_id].status, "succeeded")
            self.assertEqual(resumed.nodes[node_id].output, {"preserved": node_id})
        for node_id in (
            "keyword",
            "embed-query",
            "dense",
            "fuse",
            "expand-context",
            "read",
        ):
            state = resumed.nodes[node_id]
            self.assertEqual(state.status, "pending")
            self.assertIsNone(state.output)
            self.assertIsNone(state.error)
            self.assertIsNone(state.cost_usd)
