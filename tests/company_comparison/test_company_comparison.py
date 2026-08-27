from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from backend.features.bi.extraction_models import BiContextCell, BiRetrievedContext
from backend.features.bi.materialization_models import BiCompanyIndexEntry
from backend.features.bi.models import (
    AmountScale,
    AvailableObservation,
    BiCompany,
    BiDashboardSnapshot,
    BiEvidence,
    BiMaterializationSource,
    BiPeriod,
    BiRefreshState,
    BiSnapshotMeta,
    CompanyId,
    IndexId,
    MetricId,
    MetricSeries,
    MetricStatus,
    PeriodId,
    PeriodKind,
    RefreshStatus,
    SnapshotId,
    SnapshotStatus,
    ValueKind,
)
from backend.features.company_comparison.cache import FileComparisonResponseCache
from backend.features.company_comparison.calculator import (
    CompanyForecastData,
    ComparisonDataError,
    ComparisonObservation,
    calculate_comparison,
)
from backend.features.company_comparison.models import (
    BriefStatus,
    CompanyComparisonRequest,
)
from backend.features.company_comparison.service import (
    EVALUATION_CHARTS,
    EVALUATION_METRICS,
    CompanyComparisonService,
)


def _snapshot(
    company_id: str,
    name: str,
    values: dict[int, tuple[Decimal, Decimal]],
    *,
    liabilities: Decimal,
    assets: Decimal,
    net_debt: Decimal,
) -> BiDashboardSnapshot:
    periods = tuple(
        BiPeriod(
            period_id=PeriodId(f"fy-{year}"),
            kind=PeriodKind.FY,
            label=str(year),
            source_label=f"FY {year}",
            end_date=datetime(year, 12, 31).date(),
            ordinal=index,
        )
        for index, year in enumerate(sorted(values), start=1)
    )

    def observation(year: int, value: Decimal, metric: str) -> AvailableObservation:
        return AvailableObservation(
            period_id=PeriodId(f"fy-{year}"),
            status=MetricStatus.AVAILABLE,
            raw_value=str(value),
            normalized_value=value,
            evidence=(
                BiEvidence(
                    cell_id=f"{metric}-{year}",
                    sheet_name="Financials",
                    cell_coord=f"B{year - 2000}",
                    source_text=f"{metric} {year}: {value}",
                ),
            ),
        )

    def amount_series(
        metric_id: MetricId,
        yearly: dict[int, Decimal],
    ) -> MetricSeries:
        return MetricSeries(
            metric_id=metric_id,
            label=metric_id.value,
            value_kind=ValueKind.AMOUNT,
            currency="USD",
            scale=AmountScale.MILLIONS,
            status=MetricStatus.AVAILABLE,
            observations=tuple(
                observation(year, value, metric_id.value) for year, value in sorted(yearly.items())
            ),
        )

    end_year = max(values)
    metrics = {
        MetricId.REVENUE: amount_series(
            MetricId.REVENUE,
            {year: revenue for year, (revenue, _) in values.items()},
        ),
        MetricId.OPERATING_INCOME: amount_series(
            MetricId.OPERATING_INCOME,
            {year: income for year, (_, income) in values.items()},
        ),
        MetricId.TOTAL_LIABILITIES: amount_series(
            MetricId.TOTAL_LIABILITIES,
            {end_year: liabilities},
        ),
        MetricId.TOTAL_ASSETS: amount_series(
            MetricId.TOTAL_ASSETS,
            {end_year: assets},
        ),
        MetricId.NET_DEBT: amount_series(
            MetricId.NET_DEBT,
            {end_year: net_debt},
        ),
    }
    return BiDashboardSnapshot(
        schema_version=1,
        company=BiCompany(company_id=CompanyId(company_id), display_name=name),
        source=BiMaterializationSource(
            file_name=f"{name}.xlsm",
            workbook_hash=("a" if company_id.endswith("a") else "b") * 64,
            index_id=IndexId(f"index-{company_id}"),
        ),
        snapshot=BiSnapshotMeta(
            snapshot_id=SnapshotId(f"snapshot-{company_id}"),
            workbook_hash=("a" if company_id.endswith("a") else "b") * 64,
            status=SnapshotStatus.READY,
            generated_at=datetime.now(timezone.utc),
            catalog_version="1",
            formula_version="1",
        ),
        refresh=BiRefreshState(status=RefreshStatus.IDLE),
        periods=periods,
        metrics=metrics,
        issues=(),
    )


class FakeStore:
    def __init__(self, snapshots: tuple[BiDashboardSnapshot, ...]) -> None:
        self.snapshots = {snapshot.company.company_id: snapshot for snapshot in snapshots}

    def get_current_many(self, company_ids):
        return {
            company_id: self.snapshots[company_id]
            for company_id in company_ids
            if company_id in self.snapshots
        }

    def list_companies(self):
        return tuple(
            BiCompanyIndexEntry(
                company=snapshot.company,
                source=snapshot.source,
                current_snapshot_id=snapshot.snapshot.snapshot_id,
            )
            for snapshot in self.snapshots.values()
        )

    def get_current(self, company_id):
        return self.snapshots.get(company_id)


class FakeRetriever:
    def __init__(self) -> None:
        self.requests = []

    def retrieve(self, request):
        self.requests.append(request)
        return BiRetrievedContext(
            request_id=request.request_id,
            file_name=request.source.file_name,
            workbook_hash=request.source.workbook_hash,
            index_id=str(request.source.index_id),
            context_blocks=("verified financial context",),
            cells=(
                BiContextCell(
                    cell_id="rag-cell",
                    sheet_name="Notes",
                    cell_coord="C3",
                    source_text="RAG retrieved company explanation",
                ),
            ),
        )


class FakeCompletion:
    def __init__(self) -> None:
        self.schema_names = []

    def complete_structured(self, model, messages, schema_name, json_schema):
        self.schema_names.append(schema_name)
        if schema_name == "company_comparison_question_plan":
            question = json.loads(messages[-1]["content"])["question"]
            evaluation_type = (
                "stability"
                if "안정" in question or "부채" in question
                else "profitability"
                if "수익" in question or "영업이익" in question
                else "growth"
                if "성장" in question or "매출" in question
                else "comprehensive"
            )
            return json.dumps(
                {
                    "evaluation_type": evaluation_type,
                    "rationale": "질문의 핵심 재무 평가 관점을 분류한 결과입니다.",
                },
                ensure_ascii=False,
            )
        payload = json.loads(messages[-1]["content"])
        company_ids = payload["analysis"]["company_ids"]
        evidence = payload["allowed_evidence"]
        evidence_ids = [item["evidence_id"] for item in evidence]
        rag_evidence_id = next(item["evidence_id"] for item in evidence if item["origin"] == "rag")
        return json.dumps(
            {
                "compared_company_ids": company_ids,
                "growth": {
                    "title": "성장",
                    "body": "선택된 두 기업의 매출 성장 경로를 검증된 계산값과 원본 근거로 비교했습니다.",
                    "evidence_ids": [evidence_ids[0]],
                },
                "profitability": {
                    "title": "수익성",
                    "body": "종료연도 영업이익률을 동일한 계산 기준으로 적용하여 기업별 차이를 확인했습니다.",
                    "evidence_ids": [evidence_ids[1]],
                },
                "risk": {
                    "title": "재무 안정성",
                    "body": "총부채 대비 총자산과 순부채 원본 값을 함께 사용하여 현금 여력을 비교했습니다.",
                    "evidence_ids": [evidence_ids[2], rag_evidence_id],
                },
                "caveats": [],
            },
            ensure_ascii=False,
        )


@pytest.fixture
def snapshots() -> tuple[BiDashboardSnapshot, ...]:
    return (
        _snapshot(
            "company-a",
            "Company A",
            {2021: (Decimal("100"), Decimal("10")), 2025: (Decimal("200"), Decimal("30"))},
            liabilities=Decimal("40"),
            assets=Decimal("100"),
            net_debt=Decimal("-20"),
        ),
        _snapshot(
            "company-b",
            "Company B",
            {2021: (Decimal("200"), Decimal("20")), 2025: (Decimal("242"), Decimal("24.2"))},
            liabilities=Decimal("120"),
            assets=Decimal("200"),
            net_debt=Decimal("50"),
        ),
    )


def test_calculator_computes_metrics_and_preserves_net_debt_sign(snapshots) -> None:
    result = calculate_comparison(snapshots, 2021, 2025)

    assert result.companies[0].revenue_cagr == pytest.approx(18.9207)
    assert result.companies[0].operating_margin == pytest.approx(15.0)
    assert result.companies[0].liabilities_to_assets == pytest.approx(40.0)
    assert result.companies[0].net_debt == -20
    assert result.companies[1].revenue_cagr == pytest.approx(4.8809)
    assert result.stability_basis_year == 2025


def test_calculator_combines_actuals_with_2026_to_2028_forecasts(snapshots) -> None:
    def forecast(company_id: str, multiplier: Decimal) -> CompanyForecastData:
        observations = {}
        for year, revenue in (
            (2026, Decimal("260")),
            (2027, Decimal("300")),
            (2028, Decimal("360")),
        ):
            income = revenue * Decimal("0.15")
            observations[year] = {
                MetricId.REVENUE: ComparisonObservation(
                    normalized_value=revenue * multiplier,
                    evidence=(
                        BiEvidence(
                            cell_id=f"revenue-{company_id}-{year}",
                            sheet_name="Key_Stats",
                            cell_coord=f"N{year - 1993}",
                            source_text=f"{year} revenue estimate",
                        ),
                    ),
                    origin="rag",
                ),
                MetricId.OPERATING_INCOME: ComparisonObservation(
                    normalized_value=income * multiplier,
                    evidence=(
                        BiEvidence(
                            cell_id=f"income-{company_id}-{year}",
                            sheet_name="Key_Stats",
                            cell_coord=f"N{year - 1984}",
                            source_text=f"{year} EBIT estimate",
                        ),
                    ),
                    origin="rag",
                ),
            }
        return CompanyForecastData(company_id=company_id, observations=observations)

    result = calculate_comparison(
        snapshots,
        2021,
        2028,
        (forecast("company-a", Decimal("1")), forecast("company-b", Decimal("2"))),
    )

    assert [point.year for point in result.companies[0].points] == [2021, 2025, 2026, 2027, 2028]
    assert result.companies[0].points[-1].revenue == 360
    assert result.companies[0].operating_margin == pytest.approx(15)
    assert result.companies[0].stability_basis_year == 2025
    assert any(item.origin == "rag" for item in result.evidence)


def test_calculator_rejects_missing_common_period(snapshots) -> None:
    with pytest.raises(ComparisonDataError, match="공통으로 존재"):
        calculate_comparison(snapshots, 2020, 2025)


def test_league_combines_three_real_companies_with_fifteen_temporary_companies(
    snapshots,
) -> None:
    third = _snapshot(
        "company-c",
        "Company C",
        {2021: (Decimal("300"), Decimal("30")), 2025: (Decimal("390"), Decimal("45"))},
        liabilities=Decimal("90"),
        assets=Decimal("300"),
        net_debt=Decimal("-15"),
    )
    service = CompanyComparisonService(
        store=FakeStore((*snapshots, third)),
        retriever=FakeRetriever(),
        completion=FakeCompletion(),
    )

    result = service.league()

    assert len(result.companies) == 18
    assert {
        company.company_id
        for company in result.companies
        if not company.company_id.startswith("temp-")
    } == {
        "company-a",
        "company-b",
        "company-c",
    }
    assert sum(company.company_id.startswith("temp-") for company in result.companies) == 15


def test_service_retrieves_and_briefs_only_selected_companies(snapshots) -> None:
    retriever = FakeRetriever()
    service = CompanyComparisonService(
        store=FakeStore(snapshots),
        retriever=retriever,
        completion=FakeCompletion(),
    )

    response = service.analyze(
        CompanyComparisonRequest(
            company_ids=(CompanyId("company-b"), CompanyId("company-a")),
            start_year=2021,
            end_year=2025,
        )
    )

    assert response.brief_status is BriefStatus.READY
    assert [item.company_id for item in response.companies] == [
        "company-b",
        "company-a",
    ]
    assert {request.source.index_id for request in retriever.requests} == {
        "index-company-a",
        "index-company-b",
    }
    assert response.brief is not None
    assert set(response.brief.compared_company_ids) == {"company-a", "company-b"}
    assert any(item.origin == "rag" for item in response.evidence)
    assert {item.company_id for item in response.evidence if item.origin == "rag"} == {
        "company-a",
        "company-b",
    }
    assert response.query_analysis is None


def test_service_reuses_persistent_answer_without_rag_or_llm_cost(
    snapshots,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "comparison-cache"
    request = CompanyComparisonRequest(
        company_ids=(CompanyId("company-a"), CompanyId("company-b")),
        start_year=2021,
        end_year=2025,
        question="두 기업 중 재무적으로 더 안정적인 기업은 어디야?",
    )
    first_retriever = FakeRetriever()
    first_completion = FakeCompletion()
    first_service = CompanyComparisonService(
        store=FakeStore(snapshots),
        retriever=first_retriever,
        completion=first_completion,
        response_cache=FileComparisonResponseCache(cache_dir),
    )

    first = first_service.analyze(request)

    second_retriever = FakeRetriever()
    second_completion = FakeCompletion()
    restarted_service = CompanyComparisonService(
        store=FakeStore(snapshots),
        retriever=second_retriever,
        completion=second_completion,
        response_cache=FileComparisonResponseCache(cache_dir),
    )
    second = restarted_service.analyze(request)

    assert first.meta.cache_hit is False
    assert len(first_retriever.requests) == 2
    assert first_completion.schema_names == [
        "company_comparison_question_plan",
        "company_comparison_brief_v2",
    ]
    assert second.meta.cache_hit is True
    assert second.analysis_id == first.analysis_id
    assert second_retriever.requests == []
    assert second_completion.schema_names == []
    assert len(list(cache_dir.glob("*.json"))) == 1


def test_service_plans_question_and_retrieves_question_specific_evidence(
    snapshots,
) -> None:
    retriever = FakeRetriever()
    service = CompanyComparisonService(
        store=FakeStore(snapshots),
        retriever=retriever,
        completion=FakeCompletion(),
    )
    question = "두 기업 중 재무적으로 더 안정적인 기업은 어디야?"
    response = service.analyze(
        CompanyComparisonRequest(
            company_ids=(CompanyId("company-a"), CompanyId("company-b")),
            start_year=2021,
            end_year=2025,
            question=question,
        )
    )

    assert response.query_analysis is not None
    assert response.query_analysis.evaluation_type == "stability"
    assert response.query_analysis.chart_ids == ("stability",)
    assert set(response.query_analysis.required_metrics) == {
        MetricId.TOTAL_LIABILITIES,
        MetricId.TOTAL_ASSETS,
        MetricId.NET_DEBT,
    }
    assert all(question in request.question for request in retriever.requests)
    assert all("net_debt" in request.question for request in retriever.requests)


def test_service_keeps_calculated_results_when_rag_is_unavailable(snapshots) -> None:
    class FailingRetriever:
        def retrieve(self, request):
            raise RuntimeError("retrieval unavailable")

    service = CompanyComparisonService(
        store=FakeStore(snapshots),
        retriever=FailingRetriever(),
        completion=FakeCompletion(),
    )
    response = service.analyze(
        CompanyComparisonRequest(
            company_ids=(CompanyId("company-a"), CompanyId("company-b")),
            start_year=2021,
            end_year=2025,
        )
    )

    assert response.brief_status is BriefStatus.FAILED
    assert response.brief is None
    assert len(response.companies) == 2
    assert response.companies[0].revenue_cagr == pytest.approx(18.9207)
    assert any("RAG 근거" in warning for warning in response.warnings)


def test_three_company_comparison_keeps_rag_evidence_for_every_company(snapshots) -> None:
    third = _snapshot(
        "company-c",
        "Company C",
        {2021: (Decimal("300"), Decimal("15")), 2025: (Decimal("360"), Decimal("30"))},
        liabilities=Decimal("100"),
        assets=Decimal("300"),
        net_debt=Decimal("-10"),
    )
    retriever = FakeRetriever()
    service = CompanyComparisonService(
        store=FakeStore((*snapshots, third)),
        retriever=retriever,
        completion=FakeCompletion(),
    )
    response = service.analyze(
        CompanyComparisonRequest(
            company_ids=(
                CompanyId("company-a"),
                CompanyId("company-b"),
                CompanyId("company-c"),
            ),
            start_year=2021,
            end_year=2025,
        )
    )

    assert response.brief_status is BriefStatus.READY
    assert {item.company_id for item in response.evidence if item.origin == "rag"} == {
        "company-a",
        "company-b",
        "company-c",
    }


def test_request_rejects_duplicate_company_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        CompanyComparisonRequest(
            company_ids=(CompanyId("company-a"), CompanyId("company-a")),
            start_year=2021,
            end_year=2025,
        )


def test_question_evaluation_set_matches_server_metric_and_chart_policy() -> None:
    path = (
        Path(__file__).parents[2]
        / "backend"
        / "features"
        / "company_comparison"
        / "evaluation_set.json"
    )
    cases = json.loads(path.read_text(encoding="utf-8"))

    assert len(cases) == 12
    assert len({case["id"] for case in cases}) == len(cases)
    assert Counter(case["expected_evaluation_type"] for case in cases) == {
        "growth": 3,
        "profitability": 3,
        "stability": 3,
        "comprehensive": 3,
    }
    for case in cases:
        evaluation_type = case["expected_evaluation_type"]
        assert case["required_metrics"] == [
            metric.value for metric in EVALUATION_METRICS[evaluation_type]
        ]
        assert case["expected_chart_ids"] == [
            chart_id.value for chart_id in EVALUATION_CHARTS[evaluation_type]
        ]
