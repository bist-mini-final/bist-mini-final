from __future__ import annotations

from pathlib import Path

from backend.core.settings import CACHE_DIR
from backend.features.bi.api_services import BiApiStorePort
from backend.features.bi.fast_rag_adapter import FastRagPipelineAdapter
from backend.features.bi.fast_rag_models import FastRagPipelineSettings
from backend.features.bi.fast_rag_ports import ModuleRegistryPort, RankedCellStorePort
from backend.features.bi.metric_reader import BiStructuredCompletionAdapter
from backend.providers.openai_responses import OpenAIResponsesClient

from .cache import FileComparisonResponseCache
from .forecast_reader import ComparisonForecastReader
from .service import CompanyComparisonService


def create_company_comparison_service(
    store: BiApiStorePort,
    registry: ModuleRegistryPort,
    cell_store: RankedCellStorePort,
    completion_client: OpenAIResponsesClient,
    cache_dir: Path = CACHE_DIR,
) -> CompanyComparisonService:
    return CompanyComparisonService(
        store=store,
        retriever=FastRagPipelineAdapter(
            registry,
            cell_store,
            FastRagPipelineSettings(
                retrieval_top_k=30,
                fused_top_k=30,
                context_cell_limit=24,
            ),
        ),
        completion=BiStructuredCompletionAdapter(completion_client),
        forecast_reader=ComparisonForecastReader(cell_store),
        response_cache=FileComparisonResponseCache(
            cache_dir / "company_comparison_v2"
        ),
    )


__all__ = ["create_company_comparison_service"]
