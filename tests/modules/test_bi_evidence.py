import json
from decimal import Decimal
from unittest.mock import MagicMock

from backend.domains.bi.domain.extraction_models import (
    BiContextCell,
    BiMetricExtractionRequest,
    BiMetricReaderResponse,
    BiRetrievalRequest,
    BiRetrievedContext,
    ReaderContractFailure,
)
from backend.domains.bi.domain.models import (
    AmountScale,
    BiMaterializationSource,
    IndexId,
    MetricId,
    MetricStatus,
    PeriodId,
)
from backend.features.bi.evidence import source_cell_value
from backend.features.bi.extraction import BiMetricExtractionService
from backend.features.bi.metric_reader import BiMetricReader

SOURCE = BiMaterializationSource(
    file_name="amesoft.xlsm",
    workbook_hash="a" * 64,
    index_id=IndexId("idx-amesoft"),
)
REQUEST = BiMetricExtractionRequest(
    request_id="question-revenue-2022",
    metric_id=MetricId.REVENUE,
    period_id=PeriodId("fy-2022-12-31"),
    period_label="FY2022",
    source=SOURCE,
)


def _context(source_text: str) -> BiRetrievedContext:
    return BiRetrievedContext(
        request_id=REQUEST.request_id,
        file_name=SOURCE.file_name,
        workbook_hash=SOURCE.workbook_hash,
        index_id=SOURCE.index_id,
        context_blocks=(source_text,),
        cells=(
            BiContextCell(
                cell_id="IncomeStatement:M23",
                sheet_name="Income_Statement",
                cell_coord="M23",
                source_text=source_text,
            ),
        ),
    )


def test_source_cell_value_rejects_header_only_placeholders() -> None:
    assert source_cell_value("Sheet: Income_Statement | Cell Value: ?") is None
    assert source_cell_value("Sheet: Income_Statement | Cell Value: NA") is None
    assert source_cell_value("Sheet: Income_Statement | Cell Value: 10296") == "10296"


def test_metric_reader_does_not_send_placeholder_cells_to_the_model() -> None:
    completion = MagicMock()
    result = BiMetricReader(completion, "test-model").read(
        REQUEST,
        _context(
            "Company: AmeSoft | Sheet: Income_Statement | Row Header: Total Revenue | "
            "Column Header: 2022-12-31 | Cell Value: ?"
        ),
    )

    assert result == ReaderContractFailure(code="verifiable_evidence_missing")
    completion.complete_structured.assert_not_called()


def test_metric_reader_rebuilds_context_from_value_bearing_cells() -> None:
    valid = (
        "Company: AmeSoft | Sheet: Income_Statement | Row Header: Total Revenue | "
        "Column Header: 2022-12-31 | Cell Value: 10296"
    )
    placeholder = (
        "Company: AmeSoft | Sheet: Balance_Sheet | Row Header: Period Date | "
        "Column Header: 2022-12-31 | Cell Value: ?"
    )
    context = BiRetrievedContext(
        request_id=REQUEST.request_id,
        file_name=SOURCE.file_name,
        workbook_hash=SOURCE.workbook_hash,
        index_id=SOURCE.index_id,
        context_blocks=(placeholder, "raw retrieval hint", valid),
        cells=(
            BiContextCell(
                cell_id="IncomeStatement:M23",
                sheet_name="Income_Statement",
                cell_coord="M23",
                source_text=valid,
            ),
            BiContextCell(
                cell_id="BalanceSheet:M201",
                sheet_name="Balance_Sheet",
                cell_coord="M201",
                source_text=placeholder,
            ),
        ),
    )
    completion = MagicMock()
    completion.complete_structured.return_value = json.dumps(
        {
            "request_id": REQUEST.request_id,
            "metric_id": REQUEST.metric_id.value,
            "period_id": REQUEST.period_id,
            "status": "available",
            "raw_value": "10296",
            "normalized_value": "10296",
            "currency": "USD",
            "scale": "millions",
            "evidence_cell_ids": ["IncomeStatement:M23"],
            "notes": [],
            "reason": None,
        }
    )

    result = BiMetricReader(completion, "test-model").read(REQUEST, context)

    assert isinstance(result, BiMetricReaderResponse)
    payload = json.loads(completion.complete_structured.call_args.kwargs["messages"][1]["content"])
    assert payload["context_blocks"] == [valid]
    assert [cell["cell_id"] for cell in payload["allowed_evidence_cells"]] == [
        "IncomeStatement:M23"
    ]


class _Retriever:
    def retrieve(self, request: BiRetrievalRequest) -> BiRetrievedContext:
        return _context(
            "Company: AmeSoft | Sheet: Income_Statement | Row Header: Total Revenue | "
            "Column Header: 2022-12-31 | Cell Value: ?"
        )


class _AvailableReader:
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
            raw_value="10296",
            normalized_value=Decimal("10296"),
            currency="USD",
            scale=AmountScale.MILLIONS,
            evidence_cell_ids=(context.cells[0].cell_id,),
            notes=(),
            reason=None,
        )


class _Profiles:
    def get_for_source(self, source: BiMaterializationSource):
        return None


def test_extraction_rejects_available_result_backed_only_by_placeholder() -> None:
    result = BiMetricExtractionService(
        _Retriever(),
        _AvailableReader(),
        _Profiles(),
    ).extract_question(REQUEST, "AmeSoft FY2022 revenue")

    assert result.observation.status is MetricStatus.INVALID
    assert result.observation.reason == "available_evidence_missing"
