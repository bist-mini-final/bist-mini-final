from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from backend.platform.openai.responses import OpenAIResponseResult
from modules.common.exceptions import StorageError
from modules.storage.company_entity_extractor import (
    CompanyEntityExtractorConfigDTO,
    CompanyEntityExtractorInputDTO,
    CompanyEntityExtractorModule,
    CompanyEntityExtractorOutputDTO,
)


def test_company_entity_extractor_standalone():
    mock_llm = MagicMock()
    mock_llm.create_response.return_value = OpenAIResponseResult(
        response_id="resp_company",
        content='{"company_name": "삼성전자", "ticker": "005930", "display_name": "삼성전자 (005930)", "confidence": "high", "source": "llm"}',
        usage={"prompt_tokens": 50, "completion_tokens": 20},
        latency_seconds=0.1,
    )
    mock_pgvector = MagicMock()
    mock_catalog = MagicMock()
    mock_catalog.resolve.return_value = MagicMock()
    extractor = CompanyEntityExtractorModule(
        completion_client=mock_llm,
        pgvector_store=mock_pgvector,
        catalog=mock_catalog,
    )
    cast(Any, extractor)._sample_workbook = MagicMock(
        return_value=["[Sheet1]\n삼성전자 2023 65670"]
    )
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


def test_standard_key_stats_filename_overrides_stale_workbook_identity() -> None:
    mock_llm = MagicMock()
    mock_pgvector = MagicMock()
    extractor = CompanyEntityExtractorModule(
        completion_client=mock_llm,
        pgvector_store=mock_pgvector,
        catalog=MagicMock(),
    )
    sample_workbook = MagicMock(return_value=["Coldplay Entertainment | NYSE:CDPL"])
    cast(Any, extractor)._sample_workbook = sample_workbook

    result = CompanyEntityExtractorOutputDTO.model_validate(
        extractor.execute(
            CompanyEntityExtractorInputDTO(
                file_name="SPG_Company_KeyStats_09_meridian_logic.xlsm",
                workbook_hash="hash-meridian",
                index_id="idx_meridian",
            )
        )
    )

    assert result.company_name == "Meridian Logic"
    assert result.ticker == ""
    assert result.source == "filename"
    sample_workbook.assert_not_called()
    mock_llm.create_response.assert_not_called()


def test_company_metadata_persistence_failure_is_not_silenced():
    module = CompanyEntityExtractorModule(
        catalog=MagicMock(),
        completion_client=MagicMock(),
        pgvector_store=MagicMock(),
    )
    cast(Any, module)._sample_workbook = MagicMock(return_value=[])
    cast(Any, module.pgvector_store).update_index_company.side_effect = RuntimeError("db down")

    with pytest.raises(StorageError):
        module.run({"file_name": "acme.xlsx", "index_id": "idx_a"})
