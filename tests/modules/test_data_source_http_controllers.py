"""Focused tests for the data-source HTTP presentation controllers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.domains.data_sources.presentation.controller import (
    DataSourceHttpController,
    UpdateIndexCompanyRequestDTO,
)
from backend.domains.data_sources.presentation.ingestion_controller import IngestionHttpController


def _data_source_controller(tmp_path) -> tuple[DataSourceHttpController, MagicMock]:
    catalog = MagicMock()
    controller = DataSourceHttpController(
        processed_dir=tmp_path,
        file_storage=cast(Any, MagicMock()),
        file_service=cast(Any, MagicMock()),
        catalog=cast(Any, catalog),
    )
    return controller, catalog


def test_company_update_is_normalized_at_the_http_boundary(tmp_path) -> None:
    controller, vectors = _data_source_controller(tmp_path)
    vectors.update_index_company.return_value = True

    result = controller.update_index_company(
        "index-1",
        UpdateIndexCompanyRequestDTO(company_name="  Nexora Labs  "),
    )

    vectors.update_index_company.assert_called_once_with("index-1", "Nexora Labs")
    assert result["company_name"] == "Nexora Labs"


def test_company_update_maps_missing_index_to_not_found(tmp_path) -> None:
    controller, vectors = _data_source_controller(tmp_path)
    vectors.update_index_company.return_value = False

    with pytest.raises(HTTPException) as raised:
        controller.update_index_company(
            "missing-index",
            UpdateIndexCompanyRequestDTO(company_name="Nexora Labs"),
        )

    assert raised.value.status_code == 404


def test_ingestion_delete_cancels_active_run_before_removing_partial_index() -> None:
    jobs = MagicMock()
    runs = MagicMock()
    vectors = MagicMock()
    active_run = SimpleNamespace(status="running")
    cancelled_run = SimpleNamespace(status="cancelled")
    jobs.load.return_value = active_run
    jobs.cancel.return_value = cancelled_run
    jobs.target_index_id.return_value = "index-partial"
    vectors.list_indexes.return_value = [{"index_id": "index-partial"}]
    vectors.delete_index.return_value = True
    runs.delete.return_value = True
    controller = IngestionHttpController(
        cast(Any, jobs),
        cast(Any, runs),
        cast(Any, vectors),
    )

    result = controller.delete_job("run-1")

    jobs.cancel.assert_called_once_with("run-1")
    jobs.target_index_id.assert_called_once_with(cancelled_run)
    vectors.delete_index.assert_called_once_with("index-partial")
    runs.delete.assert_called_once_with("run-1")
    assert result["index_deleted"] is True
    assert result["source_file_preserved"] is True


def test_ingestion_delete_preserves_run_when_index_catalog_is_unavailable() -> None:
    jobs = MagicMock()
    runs = MagicMock()
    vectors = MagicMock()
    run = SimpleNamespace(status="failed")
    jobs.load.return_value = run
    jobs.target_index_id.return_value = "index-partial"
    vectors.list_indexes.side_effect = RuntimeError("database unavailable")
    controller = IngestionHttpController(
        cast(Any, jobs),
        cast(Any, runs),
        cast(Any, vectors),
    )

    with pytest.raises(HTTPException) as raised:
        controller.delete_job("run-1")

    assert raised.value.status_code == 503
    runs.delete.assert_not_called()
