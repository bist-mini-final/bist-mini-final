from hashlib import sha256
from typing import assert_never

from .extraction_models import (
    BiContextCell,
    BiRetrievalRequest,
    BiRetrievedContext,
)
from .fast_rag_models import (
    FastRagPipelineSettings,
    RankedEvidenceCell,
    RetrievalIdentity,
)
from .fast_rag_ports import ModuleRegistryPort, RankedCellStorePort
from .profile_models import BiProfileRetrievalRequest
from .rag_adapter import RagPipelineContractError
from .rag_pipeline_models import (
    RagEmbeddings,
    RagIndex,
    RagQueryContext,
    RagRankedResult,
    RagSubqueries,
)


class FastRagPipelineAdapter:
    def __init__(
        self,
        registry: ModuleRegistryPort,
        cell_store: RankedCellStorePort,
        settings: FastRagPipelineSettings | None = None,
    ) -> None:
        self._registry = registry
        self._cell_store = cell_store
        self._settings = settings or FastRagPipelineSettings()

    def retrieve(
        self,
        request: BiRetrievalRequest | BiProfileRetrievalRequest,
    ) -> BiRetrievedContext:
        identity = self._identity(request)
        query_context = RagQueryContext(
            question_id=self._question_id(identity.question),
            question_text=identity.question,
        )
        subqueries = self._decompose(query_context)
        embeddings = self._embed(subqueries)
        index = self._index_reference(identity, embeddings)
        ranked = self._retrieve_dense(embeddings, index)
        self._require_lineage(identity, ranked)
        cells = self._fetch_ranked_cells(identity, ranked)

        return BiRetrievedContext(
            request_id=identity.request_id,
            file_name=identity.file_name,
            workbook_hash=identity.workbook_hash,
            index_id=identity.index_id,
            context_blocks=tuple(self._context_block(cell) for cell in cells),
            cells=tuple(
                BiContextCell(
                    cell_id=cell.cell_id,
                    sheet_name=cell.sheet_name,
                    cell_coord=cell.cell_coord,
                    source_text=cell.source_text,
                )
                for cell in cells
            ),
        )

    @staticmethod
    def _identity(
        request: BiRetrievalRequest | BiProfileRetrievalRequest,
    ) -> RetrievalIdentity:
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
        return RetrievalIdentity(
            request_id=request_id,
            question=question,
            file_name=source.file_name,
            workbook_hash=source.workbook_hash,
            index_id=str(source.index_id),
        )

    @staticmethod
    def _question_id(question: str) -> str:
        normalized = " ".join(question.split())
        digest = sha256(normalized.encode("utf-8")).hexdigest()[:16].upper()
        return f"QUERY-{digest}"

    def _decompose(self, query_context: RagQueryContext) -> RagSubqueries:
        output = self._registry.execute(
            "decomposer",
            {"query_context": query_context.model_dump(mode="json")},
            {
                "model": self._settings.decomposer_model,
                "preset": self._settings.decomposer_preset,
            },
        )
        return RagSubqueries.model_validate(output)

    def _embed(self, subqueries: RagSubqueries) -> RagEmbeddings:
        output = self._registry.execute(
            "embedder",
            subqueries.model_dump(mode="json"),
            {"model": self._settings.embedding_model},
        )
        return RagEmbeddings.model_validate(output)

    def _index_reference(
        self,
        identity: RetrievalIdentity,
        embeddings: RagEmbeddings,
    ) -> RagIndex:
        first_embedding = next(iter(embeddings.items.values()), ())
        if not first_embedding:
            raise RagPipelineContractError(code="query_embeddings_missing")
        return RagIndex(
            index_id=identity.index_id,
            file_name=identity.file_name,
            workbook_hash=identity.workbook_hash,
            model=self._settings.embedding_model,
            dimension=len(first_embedding),
            document_count=0,
        )

    def _retrieve_dense(
        self,
        embeddings: RagEmbeddings,
        index: RagIndex,
    ) -> RagRankedResult:
        output = self._registry.execute(
            "pgvector_retriever",
            {
                "query_input": embeddings.model_dump(mode="json"),
                "index_input": index.model_dump(mode="json"),
            },
            {"top_k": self._settings.retrieval_top_k},
        )
        return RagRankedResult.model_validate(output)

    @staticmethod
    def _require_lineage(
        identity: RetrievalIdentity,
        ranked: RagRankedResult,
    ) -> None:
        if (
            ranked.document_context.file_name != identity.file_name
            or ranked.document_context.workbook_hash != identity.workbook_hash
        ):
            raise RagPipelineContractError(code="retrieval_lineage_mismatch")

    def _fetch_ranked_cells(
        self,
        identity: RetrievalIdentity,
        ranked: RagRankedResult,
    ) -> tuple[RankedEvidenceCell, ...]:
        ranked_ids = list(dict.fromkeys(item.cell_id for item in ranked.items))
        if not ranked_ids:
            raise RagPipelineContractError(code="retrieval_candidates_missing")
        raw_cells = self._cell_store.fetch_cells_by_metadata(
            cell_identifiers=ranked_ids,
            workbook_hash=identity.workbook_hash,
            collection_name=identity.index_id,
            limit=self._settings.context_cell_limit,
        )
        cells_by_id: dict[str, RankedEvidenceCell] = {}
        for raw_cell in raw_cells:
            cell = RankedEvidenceCell.model_validate(
                {
                    "cell_id": raw_cell.get("cell_id"),
                    "sheet_name": raw_cell.get("sheet_name"),
                    "cell_coord": raw_cell.get("cell_coord"),
                    "source_text": raw_cell.get("source_text"),
                }
            )
            cells_by_id.setdefault(cell.cell_id, cell)
        selected = tuple(
            cells_by_id[cell_id]
            for cell_id in ranked_ids
            if cell_id in cells_by_id
        )
        if not selected:
            raise RagPipelineContractError(code="context_cells_missing")
        return selected

    @staticmethod
    def _context_block(cell: RankedEvidenceCell) -> str:
        return (
            f"Cell ID: {cell.cell_id} | Sheet: {cell.sheet_name} | "
            f"Coordinate: {cell.cell_coord}\n{cell.source_text}"
        )
