from datetime import UTC, datetime
from decimal import Decimal
import unittest

from pydantic import ValidationError

from backend.bi.models import (
    AmountScale,
    AvailableObservation,
    BiCompany,
    BiDashboardSnapshot,
    BiEvidence,
    BiIssue,
    BiMaterializationSource,
    BiPeriod,
    BiRefreshState,
    BiSnapshotMeta,
    MetricId,
    MetricSeries,
    MetricStatus,
    PeriodKind,
    RefreshStatus,
    SnapshotStatus,
    UnavailableObservation,
    ValueKind,
)


class BiContractTests(unittest.TestCase):
    def test_dashboard_snapshot_parses_structured_metric_contract(self) -> None:
        # Given
        evidence = BiEvidence(
            cell_id="income-statement:B12",
            sheet_name="Income Statement",
            cell_coord="B12",
            source_text="FY2025 1,234.5",
        )
        observation = AvailableObservation(
            period_id="fy-2025",
            status=MetricStatus.AVAILABLE,
            raw_value="1,234.5",
            normalized_value=Decimal("1234.5"),
            evidence=(evidence,),
        )
        series = MetricSeries(
            metric_id=MetricId.REVENUE,
            label="매출",
            value_kind=ValueKind.AMOUNT,
            currency="USD",
            scale=AmountScale.MILLIONS,
            status=MetricStatus.AVAILABLE,
            observations=(observation,),
        )

        # When
        snapshot = BiDashboardSnapshot(
            schema_version=1,
            company=BiCompany(company_id="company-1", display_name="BIST"),
            source=BiMaterializationSource(
                file_name="company.xlsx",
                workbook_hash="a" * 64,
                index_id="index-1",
            ),
            snapshot=BiSnapshotMeta(
                snapshot_id="snapshot-1",
                workbook_hash="a" * 64,
                status=SnapshotStatus.READY,
                generated_at=datetime(2026, 8, 19, tzinfo=UTC),
                catalog_version="1",
                formula_version="1",
            ),
            refresh=BiRefreshState(status=RefreshStatus.IDLE),
            periods=(
                BiPeriod(
                    period_id="fy-2025",
                    kind=PeriodKind.FY,
                    label="FY2025",
                    source_label="FY0",
                    end_date=None,
                    ordinal=0,
                ),
            ),
            metrics={MetricId.REVENUE: series},
            issues=(),
        )

        # Then
        self.assertEqual(snapshot.metrics[MetricId.REVENUE].observations[0], observation)

    def test_contract_rejects_unknown_fields(self) -> None:
        # Given
        payload = {"company_id": "company-1", "display_name": "BIST", "typo": True}

        # When / Then
        with self.assertRaises(ValidationError):
            BiCompany.model_validate(payload)

    def test_available_observation_accepts_optional_evidence(self) -> None:
        # Given / When
        observation = AvailableObservation(
            period_id="fy-2025",
            status=MetricStatus.AVAILABLE,
            raw_value="1234.5",
            normalized_value=Decimal("1234.5"),
            evidence=(),
        )

        # Then
        self.assertEqual(observation.evidence, ())

    def test_unavailable_observation_preserves_missing_state(self) -> None:
        # Given / When
        observation = UnavailableObservation(
            period_id="fy-2025",
            status=MetricStatus.MISSING,
            raw_value="NA",
            normalized_value=None,
            evidence=(),
            reason="source value is missing",
        )

        # Then
        self.assertIsNone(observation.normalized_value)

    def test_materialization_source_rejects_non_hash_version(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValidationError):
            BiMaterializationSource(
                file_name="company.xlsx",
                workbook_hash="not-a-hash",
                index_id="index-1",
            )

    def test_materialization_source_rejects_file_system_path(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValidationError):
            BiMaterializationSource(
                file_name="../processed/company.xlsx",
                workbook_hash="a" * 64,
                index_id="index-1",
            )

    def test_dashboard_contract_is_frozen(self) -> None:
        # Given
        company = BiCompany(company_id="company-1", display_name="BIST")

        # When / Then
        with self.assertRaises(ValidationError):
            company.display_name = "Changed"

    def test_issue_accepts_metric_specific_warning(self) -> None:
        # Given / When
        issue = BiIssue(
            code="accounting_equation_mismatch",
            message="자산과 부채 및 자본의 합계가 일치하지 않습니다.",
            metric_id=MetricId.TOTAL_ASSETS,
        )

        # Then
        self.assertEqual(issue.metric_id, MetricId.TOTAL_ASSETS)


if __name__ == "__main__":
    unittest.main()
