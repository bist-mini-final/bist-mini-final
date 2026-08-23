from hashlib import sha256
from typing import assert_never

from modules.common.base_module import QueryContextDTO
from modules.embedding.query_embedder import EmbeddingsDTO
from modules.query.decomposer import SubqueriesDTO
from modules.query.llm_query_router import (
    LlmQueryRouterOutputDTO,
    RetrievalPlanDTO,
)
from modules.retrieval.context_expander import ContextDTO
from modules.retrieval.pgvector_retriever import RankedSearchResultDTO
from modules.retrieval.rrf_fusion import RetrievalDTO
from modules.storage.pgvector_data_scope import DataScopeCatalogDTO, DataScopeDTO

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
from .rag_errors import RagPipelineContractError


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
        query_context = QueryContextDTO(
            question_id=self._question_id(identity.question),
            question_text=identity.question,
        )
        subqueries = self._decompose(query_context)
        scope = self._data_scope(identity)
        retrieval_plan = self._route(
            subqueries,
            DataScopeCatalogDTO(collections=[scope]),
        )
        embeddings = self._embed(retrieval_plan)
        dense = self._retrieve_dense(embeddings)
        keyword = self._retrieve_keyword(retrieval_plan)
        retrieval = self._fuse(dense, keyword)
        self._require_lineage(identity, retrieval)
        context = self._expand(retrieval)
        cells = self._fetch_ranked_cells(identity, retrieval)

        return BiRetrievedContext(
            request_id=identity.request_id,
            file_name=identity.file_name,
            workbook_hash=identity.workbook_hash,
            index_id=identity.index_id,
            context_blocks=tuple(context.items),
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

    def _route(
        self,
        subqueries: SubqueriesDTO,
        scope_catalog: DataScopeCatalogDTO,
    ) -> RetrievalPlanDTO:
        output = self._registry.execute(
            "llm_query_router",
            {
                "query_input": subqueries.model_dump(mode="json"),
                "scope_catalog": scope_catalog.model_dump(mode="json"),
            },
            {"model": self._settings.decomposer_model},
        )
        return LlmQueryRouterOutputDTO.model_validate(output)

    def _decompose(
        self,
        query_context: QueryContextDTO,
    ) -> SubqueriesDTO:
        output = self._registry.execute(
            "decomposer",
            {
                "query_context": query_context.model_dump(mode="json"),
            },
            {"model": self._settings.decomposer_model},
        )
        return SubqueriesDTO.model_validate(output)

    def _embed(
        self,
        retrieval_plan: RetrievalPlanDTO,
    ) -> EmbeddingsDTO:
        output = self._registry.execute(
            "embedder",
            {
                "retrieval_plan": retrieval_plan.model_dump(mode="json"),
            },
            {},
        )
        return EmbeddingsDTO.model_validate(output)

    def _data_scope(
        self,
        identity: RetrievalIdentity,
    ) -> DataScopeDTO:
        metadata = self._cell_store.get_index_metadata(identity.index_id)
        if (
            str(metadata.get("file_name") or "") != identity.file_name
            or str(metadata.get("workbook_hash") or "") != identity.workbook_hash
        ):
            raise RagPipelineContractError(code="index_lineage_mismatch")
        model = str(metadata.get("model") or "")
        dimension = int(metadata.get("dimension") or 0)
        if not model or dimension < 1:
            raise RagPipelineContractError(code="index_embedding_contract_missing")
        raw_sheet_names = metadata.get("sheet_names") or []
        return DataScopeDTO(
            index_id=identity.index_id,
            file_name=identity.file_name,
            workbook_hash=identity.workbook_hash,
            model=model,
            dimension=dimension,
            document_count=int(metadata.get("document_count") or 0),
            company_name=str(metadata.get("company_name") or ""),
            sheet_names=[str(name) for name in raw_sheet_names],
        )

    def _retrieve_dense(
        self,
        embeddings: EmbeddingsDTO,
    ) -> RankedSearchResultDTO:
        output = self._registry.execute(
            "pgvector_retriever",
            {
                "query_input": embeddings.model_dump(mode="json"),
            },
            {"top_k": self._settings.retrieval_top_k},
        )
        return RankedSearchResultDTO.model_validate(output)

    def _retrieve_keyword(
        self,
        retrieval_plan: RetrievalPlanDTO,
    ) -> RankedSearchResultDTO:
        output = self._registry.execute(
            "postgres_native_keyword_retriever",
            {
                "retrieval_plan": retrieval_plan.model_dump(mode="json"),
            },
            {"top_k": self._settings.retrieval_top_k},
        )
        return RankedSearchResultDTO.model_validate(output)

    def _fuse(
        self,
        dense: RankedSearchResultDTO,
        keyword: RankedSearchResultDTO,
    ) -> RetrievalDTO:
        output = self._registry.execute(
            "rrf_fusion",
            {
                "dense_result": dense.model_dump(mode="json"),
                "bm25_result": keyword.model_dump(mode="json"),
            },
            {
                "rrf_k": self._settings.rrf_k,
                "top_k": self._settings.fused_top_k,
            },
        )
        return RetrievalDTO.model_validate(output)

    def _expand(self, retrieval: RetrievalDTO) -> ContextDTO:
        output = self._registry.execute(
            "pg_context_expander",
            {"retrieval_json": retrieval.model_dump(mode="json")},
            {
                "top_k": self._settings.fused_top_k,
                "max_blocks": self._settings.context_cell_limit,
            },
        )
        return ContextDTO.model_validate(output)

    @staticmethod
    def _require_lineage(
        identity: RetrievalIdentity,
        ranked: RetrievalDTO,
    ) -> None:
        if (
            ranked.document_context.file_name != identity.file_name
            or ranked.document_context.workbook_hash != identity.workbook_hash
        ):
            raise RagPipelineContractError(code="retrieval_lineage_mismatch")

    def _fetch_ranked_cells(
        self,
        identity: RetrievalIdentity,
        ranked: RetrievalDTO,
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
        if not raw_cells:
            raise RagPipelineContractError(code="context_cells_missing")

        cells_by_key: dict[str, RankedEvidenceCell] = {}
        for raw_cell in raw_cells:
            cell = RankedEvidenceCell.model_validate(
                {
                    "cell_id": raw_cell.get("cell_id"),
                    "sheet_name": raw_cell.get("sheet_name"),
                    "cell_coord": raw_cell.get("cell_coord"),
                    "source_text": raw_cell.get("source_text"),
                }
            )
            keys = [
                str(raw_cell.get("id") or ""),
                str(raw_cell.get("cell_id") or ""),
                str(raw_cell.get("cell_coord") or ""),
                f"{raw_cell.get('sheet_name')} Cell {raw_cell.get('cell_coord')}",
                f"{raw_cell.get('sheet_name')}:{raw_cell.get('cell_coord')}",
            ]
            sheet = str(raw_cell.get("sheet_name") or "")
            coord = str(raw_cell.get("cell_coord") or "")
            if sheet == "Income_Statement":
                keys.append(f"IS Cell {coord}")
            elif sheet == "Balance_Sheet":
                keys.append(f"BS Cell {coord}")
            elif sheet == "Cash_Flow":
                keys.append(f"CF Cell {coord}")
            elif sheet == "Key_Stats":
                keys.append(f"KS Cell {coord}")

            for k in keys:
                if k:
                    cells_by_key.setdefault(k, cell)

        selected_list: list[RankedEvidenceCell] = []
        seen_ids: set[str] = set()
        for cell_id in ranked_ids:
            matched = cells_by_key.get(cell_id)
            if matched and matched.cell_id not in seen_ids:
                seen_ids.add(matched.cell_id)
                selected_list.append(matched)

        if not selected_list and raw_cells:
            for raw_cell in raw_cells:
                cell = RankedEvidenceCell.model_validate(
                    {
                        "cell_id": raw_cell.get("cell_id"),
                        "sheet_name": raw_cell.get("sheet_name"),
                        "cell_coord": raw_cell.get("cell_coord"),
                        "source_text": raw_cell.get("source_text"),
                    }
                )
                if cell.cell_id not in seen_ids:
                    seen_ids.add(cell.cell_id)
                    selected_list.append(cell)

        if not selected_list:
            raise RagPipelineContractError(code="context_cells_missing")
        return tuple(selected_list[: self._settings.context_cell_limit])
