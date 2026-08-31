"""Compatibility normalization for persisted BI snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, overload

from backend.domains.bi.domain.models import MetricId

SUPPORTED_METRIC_IDS = frozenset(metric.value for metric in MetricId)


@overload
def normalize_snapshot_payload(payload: Mapping[str, Any]) -> dict[str, Any]: ...


@overload
def normalize_snapshot_payload(payload: object) -> object: ...


def normalize_snapshot_payload(payload: object) -> object:
    """Return an API-compatible snapshot view without mutating stored JSON.

    Snapshots can contain metrics written by a newer producer than this API.
    The current contract cannot deserialize those metric identifiers, so omit
    only those forward-compatible entries before Pydantic validation. Other
    malformed fields are intentionally left intact and still fail validation.
    """
    if not isinstance(payload, Mapping):
        return payload

    normalized: dict[str, Any] = dict(payload)

    metrics = payload.get("metrics")
    if isinstance(metrics, Mapping):
        normalized["metrics"] = {
            metric_id: series
            for metric_id, series in metrics.items()
            if _is_supported_metric(metric_id, series)
        }

    issues = payload.get("issues")
    if isinstance(issues, (list, tuple)):
        normalized["issues"] = [
            issue
            for issue in issues
            if not _references_unsupported_metric(issue)
        ]

    return normalized


def _is_supported_metric(metric_id: object, series: object) -> bool:
    if str(metric_id) not in SUPPORTED_METRIC_IDS:
        return False
    if not isinstance(series, Mapping) or "metric_id" not in series:
        return True
    return str(series["metric_id"]) in SUPPORTED_METRIC_IDS


def _references_unsupported_metric(issue: object) -> bool:
    if not isinstance(issue, Mapping):
        return False
    metric_id = issue.get("metric_id")
    return metric_id is not None and str(metric_id) not in SUPPORTED_METRIC_IDS


__all__ = ["normalize_snapshot_payload"]
