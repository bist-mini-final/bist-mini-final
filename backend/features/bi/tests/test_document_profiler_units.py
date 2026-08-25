from __future__ import annotations

import json
from threading import Barrier

from backend.features.bi.document_profiler import BiDocumentProfiler
from backend.features.bi.extraction_models import BiContextCell, BiRetrievedContext
from backend.features.bi.materialization_models import BiDocumentProfile
from backend.features.bi.metric_reader import JsonValue
from backend.features.bi.models import (
    AmountScale,
    BiMaterializationRequest,
    BiMaterializationSource,
    CompanyId,
    IndexId,
)
from backend.features.bi.profile_models import BiProfileRetrievalRequest


class SingleSheetCatalog:
    def list_sheets(self, source: BiMaterializationSource) -> tuple[str, ...]:
        """Return the available sheet names for a materialization source.
        
        Parameters:
        	source (BiMaterializationSource): The materialization source to inspect.
        
        Returns:
        	tuple[str, ...]: The available sheet names.
        """
        return ("Key_Stats",)


class UnitEvidenceRetriever:
    def retrieve(self, request: BiProfileRetrievalRequest) -> BiRetrievedContext:
        """
        Return unit-scale evidence for the Key_Stats sheet.
        
        Parameters:
        	request (BiProfileRetrievalRequest): Request containing the source and request metadata.
        
        Returns:
        	BiRetrievedContext: Context containing the Key_Stats!B2 evidence that FY2025 data is reported in millions.
        """
        cell = BiContextCell(
            cell_id="Key_Stats Cell B2",
            sheet_name="Key_Stats",
            cell_coord="B2",
            source_text="Sheet: Key_Stats | Row Header: Data in ($M) | Column Header: FY2025",
        )
        return BiRetrievedContext(
            request_id=request.request_id,
            file_name=request.source.file_name,
            workbook_hash=request.source.workbook_hash,
            index_id=request.source.index_id,
            context_blocks=(cell.source_text,),
            cells=(cell,),
        )


class ConcurrentProfileClient:
    def __init__(self) -> None:
        self._barrier = Barrier(2, timeout=1)

    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        json_schema: dict[str, JsonValue],
    ) -> str:
        """
        Return schema-specific structured profile data for the concurrent test request.
        
        Parameters:
            messages (list[dict[str, str]]): Messages containing the request identifier.
            schema_name (str): Discovery schema to respond to.
        
        Returns:
            str: JSON containing period or unit metadata and its evidence cell.
        
        Raises:
            AssertionError: If the schema is not supported.
        """
        self._barrier.wait()
        request_id = json.loads(messages[-1]["content"])["request_id"]
        if schema_name == "bi_period_discovery":
            return json.dumps(
                {
                    "request_id": request_id,
                    "periods": [
                        {
                            "period": {
                                "kind": "fy",
                                "label": "FY2025",
                                "source_label": "FY2025",
                                "end_date": "2025-12-31",
                                "ordinal": 2025,
                            },
                            "evidence_cell_ids": ["Key_Stats Cell B2"],
                        }
                    ],
                }
            )
        if schema_name == "bi_unit_discovery":
            return json.dumps(
                {
                    "request_id": request_id,
                    "currency": "USD",
                    "scale": "millions",
                    "evidence_cell_ids": ["Key_Stats Cell B2"],
                }
            )
        raise AssertionError(f"unexpected schema: {schema_name}")


def test_profiler_discovers_periods_and_units_concurrently() -> None:
    request = BiMaterializationRequest(
        company_id=CompanyId("company-ibm"),
        display_name="IBM",
        source=BiMaterializationSource(
            file_name="ibm.xlsx",
            workbook_hash="a" * 64,
            index_id=IndexId("index-ibm"),
        ),
    )
    profiler = BiDocumentProfiler(
        UnitEvidenceRetriever(),
        ConcurrentProfileClient(),
        "test-model",
        SingleSheetCatalog(),
    )

    result = profiler.profile(request)

    assert isinstance(result, BiDocumentProfile)
    assert result.currency == "USD"
    assert result.scale is AmountScale.MILLIONS
    assert tuple(period.label for period in result.periods) == ("FY2025",)
    assert tuple(item.cell_id for item in result.evidence) == ("Key_Stats Cell B2",)
