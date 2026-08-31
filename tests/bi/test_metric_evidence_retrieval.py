from backend.domains.bi.application.fast_rag_models import (
    FastRagPipelineSettings,
)
from backend.domains.bi.domain.extraction_models import (
    BiContextCell,
    BiMetricExtractionRequest,
    BiRetrievalRequest,
)
from backend.domains.bi.domain.models import (
    BiMaterializationSource,
    IndexId,
    MetricId,
    PeriodId,
)
from backend.domains.bi.infrastructure.integrations.fast_rag_adapter import (
    FastRagPipelineAdapter,
)
from backend.domains.bi.infrastructure.postgres.metric_evidence import _period_terms

SOURCE = BiMaterializationSource(
    file_name="financials.xlsx",
    workbook_hash="a" * 64,
    index_id=IndexId("idx-financials"),
)


class _UnusedRegistry:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("semantic pipeline must not run when exact evidence exists")


class _UnusedCellStore:
    def get_index_metadata(self, *_args, **_kwargs):
        raise AssertionError("catalog lookup must not run when exact evidence exists")

    def fetch_cells_by_metadata(self, *_args, **_kwargs):
        raise AssertionError("ranked-cell lookup must not run when exact evidence exists")


class _ExactEvidence:
    def __init__(self) -> None:
        self.limits: list[int] = []

    def retrieve_metric_cells(self, request, *, limit):
        self.limits.append(limit)
        assert request.metric_id is MetricId.OPERATING_INCOME
        return (
            BiContextCell(
                cell_id="O43",
                sheet_name="Income_Statement",
                cell_coord="O43",
                source_text=(
                    "Company: Sample | Sheet: Income_Statement | "
                    "Row Header: Operating Income | Column Header: 2024-12-31 | "
                    "Cell Value: 1730"
                ),
            ),
        )


def _request(period_id: str, period_label: str) -> BiMetricExtractionRequest:
    return BiMetricExtractionRequest(
        request_id="question-operating-income",
        metric_id=MetricId.OPERATING_INCOME,
        period_id=PeriodId(period_id),
        period_label=period_label,
        source=SOURCE,
    )


def test_exact_metric_evidence_short_circuits_generic_rag() -> None:
    evidence = _ExactEvidence()
    adapter = FastRagPipelineAdapter(
        _UnusedRegistry(),
        _UnusedCellStore(),
        FastRagPipelineSettings(exact_cell_limit=4),
        metric_evidence=evidence,
    )

    result = adapter.retrieve(
        BiRetrievalRequest(
            extraction=_request("fy-2024-12-31", "FY2024"),
            question="Find FY2024 operating income",
        )
    )

    assert result.cells[0].cell_coord == "O43"
    assert result.context_blocks == (result.cells[0].source_text,)
    assert evidence.limits == [4]


def test_period_terms_distinguish_fy_and_ltm_for_the_same_end_date() -> None:
    fy_terms, fy_kind = _period_terms(_request("fy-2025-12-31", "FY2025"))
    ltm_terms, ltm_kind = _period_terms(_request("ltm-2025-12-31", "LTM 2025"))

    assert fy_kind == "fy"
    assert ltm_kind == "ltm"
    assert "20251231" in fy_terms
    assert "20251231" in ltm_terms
    assert "fy2025" in fy_terms
    assert "ltm2025" in ltm_terms
