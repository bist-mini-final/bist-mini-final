from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, assert_never

from .extraction_models import (
    BiContextCell,
    BiRetrievalRequest,
    BiRetrievedContext,
)
from .rag_pipeline_models import (
    RagCellDocument,
    RagContext,
    RagEmbeddings,
    RagLoadedIndex,
    RagRankedResult,
    RagRetrieval,
    RagSubqueries,
    RagQueryContext,
)
from .profile_models import BiProfileRetrievalRequest


class ExistingRagModulesPort(Protocol):
    def decompose(self, query_context: RagQueryContext) -> RagSubqueries: ...

    def load_index(self, index_id: str) -> RagLoadedIndex: ...

    def embed(self, subqueries: RagSubqueries) -> RagEmbeddings: ...

    def retrieve_bm25(
        self,
        subqueries: RagSubqueries,
        loaded: RagLoadedIndex,
    ) -> RagRankedResult: ...

    def retrieve_dense(
        self,
        embeddings: RagEmbeddings,
        loaded: RagLoadedIndex,
    ) -> RagRankedResult: ...

    def fuse(
        self,
        bm25: RagRankedResult,
        dense: RagRankedResult,
    ) -> RagRetrieval: ...

    def expand(
        self,
        retrieval: RagRetrieval,
        loaded: RagLoadedIndex,
    ) -> RagContext: ...


@dataclass(frozen=True, slots=True)
class RagPipelineContractError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


class ExistingRagPipelineAdapter:
    def __init__(self, modules: ExistingRagModulesPort) -> None:
        self._modules = modules

    def retrieve(
        self,
        request: BiRetrievalRequest | BiProfileRetrievalRequest,
    ) -> BiRetrievedContext:
        match request:
            case BiRetrievalRequest(extraction=extraction, question=question):
                request_id = extraction.request_id
                source = extraction.source
            case BiProfileRetrievalRequest(
                request_id=request_id,
                source=source,
                question=question,
            ):
                pass
            case unreachable:
                assert_never(unreachable)

        normalized_question = " ".join(question.split())
        question_id = "QUERY-" + sha256(
            normalized_question.encode("utf-8")
        ).hexdigest()[:16].upper()
        subqueries = self._modules.decompose(
            RagQueryContext(question_id=question_id, question_text=question)
        )
        loaded = self._modules.load_index(str(source.index_id))
        embeddings = self._modules.embed(subqueries)
        bm25 = self._modules.retrieve_bm25(subqueries, loaded)
        dense = self._modules.retrieve_dense(embeddings, loaded)
        retrieval = self._modules.fuse(bm25, dense)
        context = self._modules.expand(retrieval, loaded)

        selected_by_id: dict[str, RagCellDocument] = {}
        for cell in loaded.document_output.items:
            marker = f"({cell.cell_id})"
            if not any(marker in block for block in context.context_blocks):
                continue
            current = selected_by_id.get(cell.cell_id)
            if current is None or cell.variant == "header_with_value":
                selected_by_id[cell.cell_id] = cell
        if not selected_by_id:
            raise RagPipelineContractError(code="context_cells_missing")

        return BiRetrievedContext(
            request_id=request_id,
            file_name=loaded.document_output.file_name,
            workbook_hash=loaded.document_output.workbook_hash,
            index_id=loaded.index_output.index_id,
            context_blocks=context.context_blocks,
            cells=tuple(
                BiContextCell(
                    cell_id=cell.cell_id,
                    sheet_name=cell.sheet_name,
                    cell_coord=cell.cell_coord,
                    source_text=cell.text,
                )
                for cell in selected_by_id.values()
            ),
        )
