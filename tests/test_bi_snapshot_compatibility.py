from copy import deepcopy
from typing import cast

import pytest
from pydantic import ValidationError

from backend.domains.bi.domain.models import BiDashboardSnapshot
from backend.features.bi.postgres_store import PostgresBiStore
from backend.features.bi.snapshot_compatibility import normalize_snapshot_payload


def _snapshot_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "company": {"company_id": "company-1", "display_name": "Example"},
        "source": {
            "file_name": "example.xlsx",
            "workbook_hash": "a" * 64,
            "index_id": "index-1",
        },
        "snapshot": {
            "snapshot_id": "snapshot-1",
            "workbook_hash": "a" * 64,
            "status": "ready",
            "generated_at": "2026-08-25T00:00:00Z",
            "catalog_version": "1",
            "formula_version": "1",
        },
        "refresh": {
            "status": "idle",
            "job_id": None,
            "started_at": None,
            "message": None,
        },
        "periods": [
            {
                "period_id": "fy-2025",
                "kind": "fy",
                "label": "2025",
                "source_label": "FY 2025",
                "end_date": "2025-12-31",
                "ordinal": 1,
            }
        ],
        "metrics": {
            "revenue": {
                "metric_id": "revenue",
                "label": "Revenue",
                "value_kind": "amount",
                "currency": "USD",
                "scale": "millions",
                "status": "available",
                "observations": [
                    {
                        "period_id": "fy-2025",
                        "status": "available",
                        "raw_value": "100",
                        "normalized_value": "100",
                        "evidence": [],
                        "notes": [],
                    }
                ],
            },
            "future_metric": {
                "metric_id": "future_metric",
                "label": "Future metric",
                "value_kind": "percent",
                "currency": None,
                "scale": None,
                "status": "available",
                "observations": [],
            },
        },
        "issues": [
            {
                "code": "revenue.checked",
                "message": "Revenue was checked.",
                "metric_id": "revenue",
            },
            {
                "code": "future_metric.checked",
                "message": "Future metric was checked.",
                "metric_id": "future_metric",
            },
        ],
    }


def test_normalize_snapshot_removes_only_unsupported_metric_references() -> None:
    payload = _snapshot_payload()
    original = deepcopy(payload)

    normalized = normalize_snapshot_payload(payload)

    assert isinstance(normalized, dict)
    assert list(normalized["metrics"]) == ["revenue"]
    original_issues = cast(list[object], original["issues"])
    assert normalized["issues"] == [original_issues[0]]
    assert payload == original
    BiDashboardSnapshot.model_validate(normalized)


def test_store_validation_accepts_snapshot_from_newer_metric_catalog() -> None:
    snapshot = PostgresBiStore._validate_snapshot(
        {"snapshot_payload": _snapshot_payload()},
        "get_current_many",
    )

    assert list(snapshot.metrics) == ["revenue"]
    assert len(snapshot.issues) == 1


def test_normalization_does_not_hide_unrelated_contract_errors() -> None:
    payload = _snapshot_payload()
    payload["company"] = {"company_id": "company-1"}

    with pytest.raises(ValidationError):
        BiDashboardSnapshot.model_validate(normalize_snapshot_payload(payload))
