from decimal import Decimal

from backend.domains.bi.application.extraction import BiMetricExtractionService
from backend.domains.bi.domain.extraction_models import (
    BiContextCell,
    BiMetricExtractionRequest,
    BiMetricReaderResponse,
    BiRetrievalRequest,
    BiRetrievedContext,
)
from backend.domains.bi.domain.materialization_models import BiDocumentProfile
from backend.domains.bi.domain.models import (
    AmountScale,
    BiMaterializationSource,
    BiPeriod,
    IndexId,
    MetricId,
    MetricStatus,
    PeriodId,
    PeriodKind,
)


class FixedRetriever:
    def retrieve(self, request: BiRetrievalRequest) -> BiRetrievedContext:
        source = request.extraction.source
        return BiRetrievedContext(
            request_id=request.extraction.request_id,
            file_name=source.file_name,
            workbook_hash=source.workbook_hash,
            index_id=source.index_id,
            context_blocks=("Total Revenue | FY2025 | 18000",),
            cells=(
                BiContextCell(
                    cell_id="KS Cell I33",
                    sheet_name="Key_Stats",
                    cell_coord="I33",
                    source_text=(
                        "Company: Bistelligence | Sheet: Key_Stats | "
                        "Row Header: Total Revenue | Column Header: FY2025 | "
                        "Cell Value: 18000"
                    ),
                ),
            ),
        )


class UnitlessReader:
    def read(
        self,
        request: BiMetricExtractionRequest,
        context: BiRetrievedContext,
    ) -> BiMetricReaderResponse:
        return BiMetricReaderResponse(
            request_id=request.request_id,
            metric_id=request.metric_id,
            period_id=request.period_id,
            status=MetricStatus.AVAILABLE,
            raw_value="18000",
            normalized_value=Decimal("18000"),
            currency=None,
            scale=None,
            evidence_cell_ids=(context.cells[0].cell_id,),
            notes=(),
            reason=None,
        )


class FixedProfileStore:
    def get_for_source(
        self,
        source: BiMaterializationSource,
    ) -> BiDocumentProfile | None:
        return BiDocumentProfile(
            periods=(
                BiPeriod(
                    period_id=PeriodId("fy-2025-12-31"),
                    kind=PeriodKind.FY,
                    label="FY2025",
                    source_label="2025-12-31",
                    end_date=None,
                    ordinal=2025,
                ),
            ),
            currency="USD",
            scale=AmountScale.MILLIONS,
        )


def test_uses_profile_units_when_metric_evidence_has_no_unit() -> None:
    source = BiMaterializationSource(
        file_name="bistelligence.xlsx",
        workbook_hash="a" * 64,
        index_id=IndexId("index-test"),
    )
    service = BiMetricExtractionService(
        FixedRetriever(),
        UnitlessReader(),
        FixedProfileStore(),
    )

    result = service.extract_question(
        BiMetricExtractionRequest(
            request_id="question-test",
            metric_id=MetricId.REVENUE,
            period_id=PeriodId("fy-2025-12-31"),
            period_label="FY2025",
            source=source,
        ),
        "question",
    )

    assert result.observation.status is MetricStatus.AVAILABLE
    assert result.currency == "USD"
    assert result.scale is AmountScale.MILLIONS
