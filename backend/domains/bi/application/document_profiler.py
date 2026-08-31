"""BI document profiling use case."""

import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from typing import Final, Protocol

from pydantic import ValidationError

from backend.domains.bi.domain.extraction_models import BiRetrievedContext
from backend.domains.bi.domain.materialization_models import (
    BiDocumentProfile,
    BiProfilingFailure,
    BiProfilingResult,
)
from backend.domains.bi.domain.models import (
    BiEvidence,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    PeriodId,
)

from .metric_reader import StructuredCompletionPort
from .profile_models import (
    BiPeriodDiscoveryReaderResponse,
    BiPeriodReaderPayload,
    BiProfileRetrievalRequest,
    BiUnitDiscoveryReaderResponse,
)

DOCUMENT_PERIOD_DISCOVERY_QUESTION: Final = (
    "이 문서에서 지표 조회에 사용할 수 있는 모든 서로 다른 FY 및 LTM 기간을 "
    "찾아라. 최신 기간만 선택하거나 "
    "같은 종류의 기간을 합치지 마라."
)
DOCUMENT_UNIT_DISCOVERY_QUESTION: Final = (
    "이 문서의 재무 금액 지표에 적용되는 통화와 원본 표시 배율을 찾아라. "
    "문서에 명시된 통화 및 단위 표기만 사용하고 추정하거나 환산하지 마라."
)
PROFILE_QUESTIONS: Final = (
    DOCUMENT_PERIOD_DISCOVERY_QUESTION,
    DOCUMENT_UNIT_DISCOVERY_QUESTION,
)


class ProfileRetrievalPort(Protocol):
    def retrieve(self, request: BiProfileRetrievalRequest) -> BiRetrievedContext: ...


class ProfileSheetCatalogPort(Protocol):
    def list_sheets(
        self,
        source: BiMaterializationSource,
    ) -> tuple[str, ...]: ...


class BiDocumentProfiler:
    def __init__(
        self,
        retriever: ProfileRetrievalPort,
        client: StructuredCompletionPort,
        model: str,
        sheet_catalog: ProfileSheetCatalogPort | None = None,
    ) -> None:
        self._retriever = retriever
        self._client = client
        self._model = model
        self._sheet_catalog = sheet_catalog

    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult:
        """
        Build a document profile from indexed workbook context.

        Parameters:
        	request (BiMaterializationRequest): Request identifying the workbook and source index to profile.

        Returns:
        	BiProfilingResult: A document profile containing discovered periods, currency, scale, relevant sheets, and trusted evidence, or a profiling failure describing why profiling could not be completed.
        """
        request_id = self._request_id(request)
        profile_requests = self._profile_requests(request, request_id)
        if not profile_requests:
            return BiProfilingFailure(
                code="profile_sheets_missing",
                message="indexed workbook does not expose profileable sheets",
            )
        contexts = tuple(
            self._retriever.retrieve(profile_request)
            for profile_request in profile_requests
        )
        if any(
            not self._lineage_matches(request, request_id, context)
            for context in contexts
        ):
            return BiProfilingFailure(
                code="retrieval_lineage_mismatch",
                message="retrieved profile context does not match the source request",
            )
        context = self._merge_contexts(contexts)

        evidence_payload = [
            {
                "cell_id": cell.cell_id,
                "sheet_name": cell.sheet_name,
                "cell_coord": cell.cell_coord,
                "source_text": cell.source_text,
            }
            for cell in context.cells
        ]
        period_payload = json.dumps(
            {
                "request_id": request_id,
                "question": DOCUMENT_PERIOD_DISCOVERY_QUESTION,
                "allowed_evidence_cells": evidence_payload,
                "context_blocks": context.context_blocks,
            },
            ensure_ascii=False,
        )
        unit_payload = json.dumps(
            {
                "request_id": request_id,
                "question": DOCUMENT_UNIT_DISCOVERY_QUESTION,
                "allowed_evidence_cells": evidence_payload,
                "context_blocks": context.context_blocks,
            },
            ensure_ascii=False,
        )
        try:
            with ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="bi-document-profile",
            ) as executor:
                period_future = executor.submit(
                    self._complete_period_discovery,
                    period_payload,
                )
                unit_future = executor.submit(
                    self._complete_unit_discovery,
                    unit_payload,
                )
                period_response = period_future.result()
                unit_response = unit_future.result()
        except ValidationError:
            return BiProfilingFailure(
                code="invalid_profile_payload",
                message="document profile did not match the structured contract",
            )
        if (
            period_response.request_id != request_id
            or unit_response.request_id != request_id
        ):
            return BiProfilingFailure(
                code="profile_identity_mismatch",
                message="document profile response does not match the request",
            )

        period_evidence_ids = tuple(
            cell_id
            for item in period_response.periods
            for cell_id in item.evidence_cell_ids
        )
        evidence = self._trusted_evidence(
            context,
            period_evidence_ids + unit_response.evidence_cell_ids,
        )
        relevant_sheets = tuple(dict.fromkeys(item.sheet_name for item in evidence))
        try:
            return BiDocumentProfile(
                periods=tuple(
                    self._canonical_period(item.period)
                    for item in period_response.periods
                ),
                currency=unit_response.currency,
                scale=unit_response.scale,
                relevant_sheets=relevant_sheets,
                evidence=evidence,
            )
        except (ValidationError, ValueError):
            return BiProfilingFailure(
                code="invalid_profile_payload",
                message="document profile did not match the structured contract",
            )

    def _complete_period_discovery(
        self,
        payload: str,
    ) -> BiPeriodDiscoveryReaderResponse:
        """
        Extract structured financial period information from the provided document context.

        Parameters:
            payload (str): Document context supplied to the structured completion client.

        Returns:
            BiPeriodDiscoveryReaderResponse: Validated discovered periods and their supporting evidence.
        """
        raw_response = self._client.complete_structured(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "재무 문서의 기간을 구조화한다. "
                        "allowed_evidence_cells의 cell_id만 근거로 사용하고 "
                        "각 기간은 별도 항목으로 반환한다."
                    ),
                },
                {"role": "user", "content": payload},
            ],
            schema_name="bi_period_discovery",
            json_schema=BiPeriodDiscoveryReaderResponse.model_json_schema(),
        )
        return BiPeriodDiscoveryReaderResponse.model_validate_json(raw_response)

    def _complete_unit_discovery(
        self,
        payload: str,
    ) -> BiUnitDiscoveryReaderResponse:
        """Identify the explicitly stated currency and display scale in financial document context.

        Parameters:
            payload (str): Structured document context used to identify the currency and display scale.

        Returns:
            BiUnitDiscoveryReaderResponse: The validated currency, display scale, and supporting evidence."""
        raw_response = self._client.complete_structured(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "재무 문서의 금액 통화와 표시 배율을 구조화한다. "
                        "allowed_evidence_cells의 cell_id만 근거로 사용한다. "
                        "문서에 명시된 표기만 사용하고 환산하거나 추정하지 않는다. "
                        "currency는 ISO 4217 3자리 대문자 코드만 사용한다. "
                        "근거의 '$' 또는 '$M' 표기는 USD로 정규화한다. "
                        "통화 또는 배율을 특정할 수 없으면 해당 필드를 null로 반환한다."
                    ),
                },
                {"role": "user", "content": payload},
            ],
            schema_name="bi_unit_discovery",
            json_schema=BiUnitDiscoveryReaderResponse.model_json_schema(),
        )
        return BiUnitDiscoveryReaderResponse.model_validate_json(raw_response)

    @staticmethod
    def _request_id(request: BiMaterializationRequest) -> str:
        """
        Create a deterministic profile request identifier from the request's company, workbook, and index identity.

        Parameters:
        	request (BiMaterializationRequest): Materialization request whose source identity is used to generate the identifier.

        Returns:
        	str: A profile-prefixed hexadecimal identifier.
        """
        identity = (
            f"{request.company_id}:{request.source.workbook_hash}:"
            f"{request.source.index_id}"
        )
        return "profile-" + sha256(identity.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _lineage_matches(
        request: BiMaterializationRequest,
        request_id: str,
        context: BiRetrievedContext,
    ) -> bool:
        return (
            context.request_id == request_id
            and context.file_name == request.source.file_name
            and context.workbook_hash == request.source.workbook_hash
            and context.index_id == request.source.index_id
        )

    @staticmethod
    def _trusted_evidence(
        context: BiRetrievedContext,
        evidence_cell_ids: tuple[str, ...],
    ) -> tuple[BiEvidence, ...]:
        cells_by_id = {cell.cell_id: cell for cell in context.cells}
        unique_ids = tuple(
            cell_id
            for cell_id in dict.fromkeys(evidence_cell_ids)
            if cell_id in cells_by_id
        )
        return tuple(
            BiEvidence(
                cell_id=cells_by_id[cell_id].cell_id,
                sheet_name=cells_by_id[cell_id].sheet_name,
                cell_coord=cells_by_id[cell_id].cell_coord,
                source_text=cells_by_id[cell_id].source_text,
            )
            for cell_id in unique_ids
        )

    @staticmethod
    def _merge_contexts(
        contexts: tuple[BiRetrievedContext, ...],
    ) -> BiRetrievedContext:
        first = contexts[0]
        cells = {
            cell.cell_id: cell
            for context in contexts
            for cell in context.cells
        }
        return BiRetrievedContext(
            request_id=first.request_id,
            file_name=first.file_name,
            workbook_hash=first.workbook_hash,
            index_id=first.index_id,
            context_blocks=tuple(
                dict.fromkeys(
                    block
                    for context in contexts
                    for block in context.context_blocks
                )
            ),
            cells=tuple(cells.values()),
        )

    @staticmethod
    def _canonical_period(period: BiPeriodReaderPayload) -> BiPeriod:
        if period.end_date is not None:
            period_key = period.end_date.isoformat()
        else:
            normalized_label = " ".join(period.source_label.split()).casefold()
            period_key = sha256(normalized_label.encode("utf-8")).hexdigest()[:16]
        return BiPeriod(
            period_id=PeriodId(f"{period.kind.value}-{period_key}"),
            kind=period.kind,
            label=period.label,
            source_label=period.source_label,
            end_date=period.end_date,
            ordinal=period.ordinal,
        )

    def _profile_requests(
        self,
        request: BiMaterializationRequest,
        request_id: str,
    ) -> tuple[BiProfileRetrievalRequest, ...]:
        """
        Builds profile retrieval requests for the configured workbook scope.

        Parameters:
        	request (BiMaterializationRequest): Materialization request containing the source workbook.
        	request_id (str): Identifier shared by the generated retrieval requests.

        Returns:
        	tuple[BiProfileRetrievalRequest, ...]: Retrieval requests for the profile questions or each workbook sheet.
        """
        if self._sheet_catalog is None:
            return tuple(
                BiProfileRetrievalRequest(
                    request_id=request_id,
                    source=request.source,
                    question=question,
                )
                for question in PROFILE_QUESTIONS
            )
        return tuple(
            BiProfileRetrievalRequest(
                request_id=request_id,
                source=request.source,
                sheet_name=sheet_name,
                question=(
                    f"{DOCUMENT_PERIOD_DISCOVERY_QUESTION} "
                    f"{DOCUMENT_UNIT_DISCOVERY_QUESTION}"
                ),
            )
            for sheet_name in self._sheet_catalog.list_sheets(request.source)
        )
