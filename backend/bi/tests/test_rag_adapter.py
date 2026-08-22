import unittest

from backend.bi.extraction_models import BiMetricExtractionRequest, BiRetrievalRequest
from backend.bi.models import BiMaterializationSource, MetricId
from backend.bi.profile_models import BiProfileRetrievalRequest
from backend.bi.rag_adapter import ExistingRagPipelineAdapter
from backend.bi.rag_pipeline_models import (
    RagCellDocument,
    RagContext,
    RagDocument,
    RagDocumentContext,
    RagEmbeddings,
    RagFusedCandidate,
    RagIndex,
    RagLoadedIndex,
    RagQueryContext,
    RagRankedCandidate,
    RagRankedResult,
    RagRetrieval,
    RagSubqueries,
)


class FakeRagModules:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def decompose(self, query_context: RagQueryContext) -> RagSubqueries:
        self.calls.append("decomposer")
        return RagSubqueries(
            query_context=query_context,
            subqueries=("Revenue FY2025",),
        )

    def load_index(self, index_id: str) -> RagLoadedIndex:
        self.calls.append("pgvector_collection_loader")
        return RagLoadedIndex(
            document_output=RagDocument(
                file_name="company.xlsx",
                workbook_hash="a" * 64,
                items=(
                    RagCellDocument(
                        cell_id="income:B12",
                        sheet_name="Income Statement",
                        cell_coord="B12",
                        row_header=("Revenue",),
                        column_header=("FY2025",),
                        cell_value="1,234.5",
                        variant="header_with_value",
                        text="FY2025 Revenue 1,234.5",
                    ),
                    RagCellDocument(
                        cell_id="other:C3",
                        sheet_name="Other",
                        cell_coord="C3",
                        row_header=("Other",),
                        column_header=("FY2025",),
                        cell_value="10",
                        variant="header_with_value",
                        text="unrelated cell",
                    ),
                ),
            ),
            index_output=RagIndex(
                index_id=index_id,
                file_name="company.xlsx",
                workbook_hash="a" * 64,
                model="fake-embedding",
                dimension=1,
                document_count=2,
            ),
        )

    def embed(self, decomposed: RagSubqueries) -> RagEmbeddings:
        self.calls.append("embedder")
        return RagEmbeddings(
            query_context=decomposed.query_context,
            items={decomposed.subqueries[0]: (1.0,)},
        )

    def retrieve_bm25(
        self,
        decomposed: RagSubqueries,
        loaded: RagLoadedIndex,
    ) -> RagRankedResult:
        self.calls.append("bm25_retriever")
        return self._ranked(decomposed.query_context, loaded)

    def retrieve_dense(
        self,
        embedded: RagEmbeddings,
        loaded: RagLoadedIndex,
    ) -> RagRankedResult:
        self.calls.append("pgvector_retriever")
        return self._ranked(embedded.query_context, loaded)

    def fuse(
        self,
        bm25: RagRankedResult,
        dense: RagRankedResult,
    ) -> RagRetrieval:
        self.calls.append("rrf_fusion")
        return RagRetrieval(
            query_context=bm25.query_context,
            document_context=bm25.document_context,
            items=(
                RagFusedCandidate(
                    rank=1,
                    cell_id="income:B12",
                    rrf_score=1.0,
                    text="FY2025 Revenue 1,234.5",
                    matched_subquery="Revenue FY2025",
                ),
            ),
        )

    def expand(
        self,
        retrieval: RagRetrieval,
        loaded: RagLoadedIndex,
    ) -> RagContext:
        self.calls.append("context")
        block = "Sheet: Income Statement | [FY2025 (income:B12)]: 1,234.5"
        return RagContext(
            query_context=retrieval.query_context,
            document_context=retrieval.document_context,
            top_k_used=1,
            adjacent_radius=3,
            context_characters=len(block),
            context_blocks=(
                "Sheet: Income Statement | [FY2025 (income:B12)]: 1,234.5",
            ),
            block_count=1,
        )

    @staticmethod
    def _ranked(
        query_context: RagQueryContext,
        loaded: RagLoadedIndex,
    ) -> RagRankedResult:
        return RagRankedResult(
            query_context=query_context,
            document_context=RagDocumentContext(
                file_name=loaded.document_output.file_name,
                workbook_hash=loaded.document_output.workbook_hash,
            ),
            items=(
                RagRankedCandidate(
                    rank=1,
                    cell_id="income:B12",
                    score=1.0,
                    text="FY2025 Revenue 1,234.5",
                    matched_subquery="Revenue FY2025",
                ),
            ),
        )


def retrieval_request() -> BiRetrievalRequest:
    return BiRetrievalRequest(
        extraction=BiMetricExtractionRequest(
            request_id="request-1",
            metric_id=MetricId.REVENUE,
            period_id="fy-2025",
            period_label="FY2025",
            source=BiMaterializationSource(
                file_name="company.xlsx",
                workbook_hash="a" * 64,
                index_id="index-1",
            ),
        ),
        question="revenue FY2025",
    )


class ExistingRagPipelineAdapterTests(unittest.TestCase):
    def test_executes_existing_pipeline_only_through_context(self) -> None:
        # Given
        modules = FakeRagModules()
        adapter = ExistingRagPipelineAdapter(modules)

        # When
        result = adapter.retrieve(retrieval_request())

        # Then
        self.assertEqual(
            modules.calls,
            [
                "decomposer",
                "pgvector_collection_loader",
                "embedder",
                "bm25_retriever",
                "pgvector_retriever",
                "rrf_fusion",
                "context",
            ],
        )
        self.assertEqual(result.cells[0].cell_id, "income:B12")
        self.assertEqual(len(result.cells), 1)

    def test_accepts_document_profile_retrieval_request(self) -> None:
        # Given
        modules = FakeRagModules()
        adapter = ExistingRagPipelineAdapter(modules)
        source = retrieval_request().extraction.source
        request = BiProfileRetrievalRequest(
            request_id="profile-1",
            source=source,
            question="period and unit profile",
        )

        # When
        result = adapter.retrieve(request)

        # Then
        self.assertEqual(result.request_id, "profile-1")
        self.assertEqual(result.workbook_hash, source.workbook_hash)


if __name__ == "__main__":
    unittest.main()
