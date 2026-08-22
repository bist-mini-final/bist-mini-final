from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from backend.providers.llm.chat_completion import ChatCompletionResult
from modules.common.exceptions import StorageError
from modules.storage.company_entity_extractor import (
    CompanyEntityExtractorConfigDTO,
    CompanyEntityExtractorInputDTO,
    CompanyEntityExtractorModule,
    CompanyEntityExtractorOutputDTO,
)


def test_company_entity_extractor_standalone():
    extractor = CompanyEntityExtractorModule()
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"company_name": "삼성전자", "ticker": "005930", "display_name": "삼성전자 (005930)", "confidence": "high", "source": "llm"}',
        usage={"prompt_tokens": 50, "completion_tokens": 20},
        latency_seconds=0.1,
    )
    extractor.completion_client = mock_llm
    extractor.catalog = MagicMock()
    extractor.catalog.resolve.return_value = MagicMock()
    extractor._sample_workbook = MagicMock(return_value=["[Sheet1]\n삼성전자 2023 65670"])
    mock_pgvector = MagicMock()
    extractor.pgvector_store = mock_pgvector

    input_dto = CompanyEntityExtractorInputDTO(
        file_name="samsung_electronics.xlsx",
        workbook_hash="dummy",
        sheet_names=["Sheet1"],
    )
    res = extractor.execute(input_dto, config=CompanyEntityExtractorConfigDTO())
    validated = CompanyEntityExtractorOutputDTO.model_validate(res)

    assert validated.company_name == "삼성전자"
    assert validated.ticker == "005930"
    assert validated.display_name == "삼성전자 (005930)"


def test_company_metadata_persistence_failure_is_not_silenced():
    module = CompanyEntityExtractorModule(
        catalog=MagicMock(),
        completion_client=MagicMock(),
        pgvector_store=MagicMock(),
    )
    module._sample_workbook = MagicMock(return_value=[])
    module.pgvector_store.update_index_company.side_effect = RuntimeError("db down")

    with pytest.raises(StorageError):
        module.run({"file_name": "acme.xlsx", "index_id": "idx_a"})
