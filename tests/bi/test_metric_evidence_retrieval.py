from backend.domains.bi.application.fast_rag_models import (
    FastRagPipelineSettings,
)
from backend.domains.bi.domain.catalog import METRIC_CATALOG, SourceMetricDefinition
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
from backend.domains.bi.infrastructure.postgres.metric_evidence import (
    _ordered_metric_aliases,
    _period_terms,
    _prioritize_metric_cells,
)

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


def _revenue_cell(cell_id: str, row_header: str, value: str) -> BiContextCell:
    return BiContextCell(
        cell_id=cell_id,
        sheet_name="Income_Statement",
        cell_coord=cell_id,
        source_text=(
            "Company: IBM | Sheet: Income_Statement | "
            f"Row Header: {row_header} | Column Header: 2024-12-31 | "
            f"Cell Value: {value}"
        ),
    )


def _revenue_definition() -> SourceMetricDefinition:
    definition = METRIC_CATALOG[MetricId.REVENUE]
    assert isinstance(definition, SourceMetricDefinition)
    return definition


def test_metric_alias_priority_prefers_canonical_label_over_broader_aliases() -> None:
    definition = _revenue_definition()

    selected = _prioritize_metric_cells(
        (
            _revenue_cell("O16", "Revenue", "62044"),
            _revenue_cell("O122", "As-Reported Total Revenue", "62753"),
            _revenue_cell("O23", "Total Revenue", "62753"),
        ),
        definition,
        limit=8,
    )

    assert [cell.cell_id for cell in selected] == ["O23"]
    assert _ordered_metric_aliases(definition)[0] == "totalrevenue"


def test_metric_alias_priority_keeps_all_canonical_cells_for_conflict_validation() -> None:
    definition = _revenue_definition()

    selected = _prioritize_metric_cells(
        (
            _revenue_cell("O16", "Revenue", "62044"),
            _revenue_cell("O23", "Total Revenue", "62753"),
            _revenue_cell("H33", "Total Revenue", "62754"),
        ),
        definition,
        limit=8,
    )

    assert [cell.cell_id for cell in selected] == ["O23", "H33"]


def test_metric_alias_priority_falls_back_when_canonical_label_is_absent() -> None:
    definition = _revenue_definition()

    selected = _prioritize_metric_cells(
        (
            _revenue_cell("O122", "As-Reported Total Revenue", "62753"),
            _revenue_cell("O16", "Revenue", "62044"),
        ),
        definition,
        limit=8,
    )

    assert [cell.cell_id for cell in selected] == ["O16"]
