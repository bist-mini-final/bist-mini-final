from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.bi.catalog import METRIC_CATALOG, SourceMetricDefinition
from backend.bi.extraction_models import (
    BiMetricExtractionRequest,
    BiMetricExtractionResult,
)
from backend.bi.materialization_models import BiDocumentProfile, BiProfilingFailure
from backend.bi.materializer import BiMaterializer, BiMaterializerServices
from backend.bi.models import (
    AmountScale,
    AvailableObservation,
    BiCompany,
    BiDashboardSnapshot,
    BiEvidence,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    BiRefreshState,
    BiSnapshotMeta,
    JobId,
    MaterializationStatus,
    MetricId,
    MetricStatus,
    PeriodKind,
    RefreshStatus,
    SnapshotStatus,
    UnavailableObservation,
    ValueKind,
)
from backend.bi.snapshot_store import FileBiSnapshotStore


NOW = datetime(2026, 8, 19, tzinfo=UTC)
SOURCE_VALUES = {
    MetricId.REVENUE: (Decimal("100"), Decimal("120")),
    MetricId.OPERATING_INCOME: (Decimal("10"), Decimal("18")),
    MetricId.NET_INCOME: (Decimal("5"), Decimal("12")),
    MetricId.OPERATING_CASH_FLOW: (Decimal("20"), Decimal("30")),
    MetricId.CAPITAL_EXPENDITURE: (Decimal("-5"), Decimal("-8")),
    MetricId.CASH_AND_SHORT_TERM_INVESTMENTS: (Decimal("40"), Decimal("45")),
    MetricId.SHORT_TERM_DEBT: (Decimal("5"), Decimal("6")),
    MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT: (Decimal("2"), Decimal("3")),
    MetricId.LONG_TERM_DEBT: (Decimal("20"), Decimal("21")),
    MetricId.TOTAL_ASSETS: (Decimal("100"), Decimal("120")),
    MetricId.TOTAL_LIABILITIES: (Decimal("60"), Decimal("70")),
    MetricId.TOTAL_EQUITY: (Decimal("40"), Decimal("50")),
}


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FakeProfiler:
    def __init__(self, result: BiDocumentProfile | BiProfilingFailure) -> None:
        self.result = result

    def profile(
        self,
        request: BiMaterializationRequest,
    ) -> BiDocumentProfile | BiProfilingFailure:
        return self.result


class FakeExtractor:
    def __init__(self, missing_metric: MetricId | None = None) -> None:
        self.missing_metric = missing_metric
        self.requests: list[BiMetricExtractionRequest] = []

    def extract(
        self,
        request: BiMetricExtractionRequest,
    ) -> BiMetricExtractionResult:
        self.requests.append(request)
        definition = METRIC_CATALOG[request.metric_id]
        if request.metric_id is MetricId.TOTAL_DEBT or request.metric_id is self.missing_metric:
            observation = UnavailableObservation(
                period_id=request.period_id,
                status=MetricStatus.MISSING,
                reason="source_value_missing",
            )
        else:
            period_index = 0 if request.period_id == "fy-2024" else 1
            value = SOURCE_VALUES[request.metric_id][period_index]
            observation = AvailableObservation(
                period_id=request.period_id,
                status=MetricStatus.AVAILABLE,
                raw_value=str(value),
                normalized_value=value,
                evidence=(
                    BiEvidence(
                        cell_id=f"{request.metric_id.value}:{request.period_id}",
                        sheet_name="Financials",
                        cell_coord=f"B{10 + list(MetricId).index(request.metric_id)}",
                        source_text=str(value),
                    ),
                ),
            )
        return BiMetricExtractionResult(
            metric_id=request.metric_id,
            period_id=request.period_id,
            value_kind=definition.value_kind,
            currency="USD",
            scale=AmountScale.MILLIONS,
            observation=observation,
        )


def profile() -> BiDocumentProfile:
    return BiDocumentProfile(
        periods=(
            BiPeriod(
                period_id="fy-2024",
                kind=PeriodKind.FY,
                label="FY2024",
                source_label="FY-1",
                end_date=None,
                ordinal=1,
            ),
            BiPeriod(
                period_id="fy-2025",
                kind=PeriodKind.FY,
                label="FY2025",
                source_label="FY0",
                end_date=None,
                ordinal=2,
            ),
        ),
        currency="USD",
        scale=AmountScale.MILLIONS,
        relevant_sheets=("Income Statement",),
        evidence=(
            BiEvidence(
                cell_id="header:B2",
                sheet_name="Financials",
                cell_coord="B2",
                source_text="FY2024 FY2025 USD millions",
            ),
        ),
    )


def request() -> BiMaterializationRequest:
    return BiMaterializationRequest(
        company_id="company-1",
        display_name="BIST",
        source=BiMaterializationSource(
            file_name="company.xlsx", workbook_hash="a" * 64, index_id="index-1"
        ),
    )


def previous_snapshot() -> BiDashboardSnapshot:
    return BiDashboardSnapshot(
        schema_version=1,
        company=BiCompany(company_id="company-1", display_name="BIST"),
        source=BiMaterializationSource(
            file_name="previous.xlsx", workbook_hash="b" * 64, index_id="index-previous"
        ),
        snapshot=BiSnapshotMeta(
            snapshot_id="snapshot-previous",
            workbook_hash="b" * 64,
            status=SnapshotStatus.READY,
            generated_at=NOW,
            catalog_version="1",
            formula_version="1",
        ),
        refresh=BiRefreshState(status=RefreshStatus.IDLE),
        periods=(),
        metrics={},
        issues=(),
    )


class BiMaterializerTests(unittest.TestCase):
    def test_registers_company_before_first_profile_failure(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            materializer = BiMaterializer(
                BiMaterializerServices(
                    FakeProfiler(
                        BiProfilingFailure(
                            code="period_profile_missing",
                            message="periods not found",
                        )
                    ),
                    FakeExtractor(),
                    store,
                    FixedClock(),
                )
            )

            # When
            materializer.materialize(request(), JobId("job-first-failure"))

            # Then
            self.assertEqual(
                store.list_companies()[0].company.company_id,
                request().company_id,
            )
            self.assertIsNone(store.list_companies()[0].current_snapshot_id)

    def test_materializes_source_and_derived_metrics_then_publishes_ready(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            extractor = FakeExtractor()
            materializer = BiMaterializer(
                BiMaterializerServices(FakeProfiler(profile()), extractor, store, FixedClock())
            )

            # When
            outcome = materializer.materialize(request(), JobId("job-1"))

            # Then
            self.assertEqual(outcome.job.status, MaterializationStatus.READY)
            self.assertEqual(
                outcome.snapshot.metrics[MetricId.REVENUE_YOY_GROWTH]
                .observations[1]
                .normalized_value,
                Decimal("20.0"),
            )
            self.assertEqual(
                outcome.snapshot.metrics[MetricId.TOTAL_DEBT]
                .observations[1]
                .normalized_value,
                Decimal("30"),
            )
            source_count = sum(
                isinstance(definition, SourceMetricDefinition)
                for definition in METRIC_CATALOG.values()
            )
            self.assertEqual(len(extractor.requests), source_count * 2)
            self.assertEqual(store.get_current(request().company_id), outcome.snapshot)

    def test_publishes_partial_snapshot_when_primary_metric_is_unavailable(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            materializer = BiMaterializer(
                BiMaterializerServices(
                    FakeProfiler(profile()),
                    FakeExtractor(missing_metric=MetricId.NET_INCOME),
                    store,
                    FixedClock(),
                )
            )

            # When
            outcome = materializer.materialize(request(), JobId("job-2"))

            # Then
            self.assertEqual(outcome.job.status, MaterializationStatus.PARTIAL)
            self.assertEqual(outcome.snapshot.snapshot.status, SnapshotStatus.PARTIAL)
            self.assertEqual(store.get_current(request().company_id), outcome.snapshot)

    def test_profiling_failure_keeps_previous_snapshot_current(self) -> None:
        # Given
        with TemporaryDirectory() as directory:
            store = FileBiSnapshotStore(Path(directory))
            previous = previous_snapshot()
            store.publish(previous)
            materializer = BiMaterializer(
                BiMaterializerServices(
                    FakeProfiler(
                        BiProfilingFailure(
                            code="period_profile_missing",
                            message="periods not found",
                        )
                    ),
                    FakeExtractor(),
                    store,
                    FixedClock(),
                )
            )

            # When
            outcome = materializer.materialize(request(), JobId("job-3"))

            # Then
            self.assertEqual(outcome.job.status, MaterializationStatus.FAILED)
            self.assertIsNone(outcome.snapshot)
            self.assertEqual(store.get_current(request().company_id), previous)


if __name__ == "__main__":
    unittest.main()
