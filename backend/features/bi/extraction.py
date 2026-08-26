from typing import Final, Literal, Protocol, assert_never, cast

from .catalog import METRIC_CATALOG, DerivedMetricDefinition, SourceMetricDefinition
from .extraction_models import (
    BiMetricExtractionRequest,
    BiMetricExtractionResult,
    BiMetricExtractionStatusError,
    BiMetricReaderResponse,
    BiRetrievalRequest,
    BiRetrievedContext,
    MetricReaderResult,
    ReaderContractFailure,
)
from .materialization_models import BiDocumentProfile
from .models import (
    AmountScale,
    AvailableObservation,
    BiEvidence,
    BiMaterializationSource,
    MetricStatus,
    UnavailableObservation,
    ValueKind,
)

MISSING_TOKENS: Final = frozenset(
    {"", "-", "NA", "N/A", "NM", "#PEND", "NULL"}
)


class ExistingRagRetrievalPort(Protocol):
    def retrieve(self, request: BiRetrievalRequest) -> BiRetrievedContext: ...


class MetricReaderPort(Protocol):
    def read(
        self,
        request: BiMetricExtractionRequest,
        context: BiRetrievedContext,
    ) -> MetricReaderResult: ...


class BiMetricUnitProfilePort(Protocol):
    def get_for_source(
        self,
        source: BiMaterializationSource,
    ) -> BiDocumentProfile | None: ...


class BiMetricExtractionService:
    def __init__(
        self,
        retriever: ExistingRagRetrievalPort,
        reader: MetricReaderPort,
        profiles: BiMetricUnitProfilePort,
    ) -> None:
        self._retriever = retriever
        self._reader = reader
        self._profiles = profiles

    def extract(
        self,
        request: BiMetricExtractionRequest,
    ) -> BiMetricExtractionResult:
        definition = METRIC_CATALOG[request.metric_id]
        if isinstance(definition, DerivedMetricDefinition):
            return self._invalid(request, definition.value_kind, "derived_metric_requires_calculation")
        if not isinstance(definition, SourceMetricDefinition):
            return self._invalid(request, definition.value_kind, "unsupported_metric_definition")
        question = definition.question_template.format(
            period_label=request.period_label,
            metric_label=definition.label_en,
        )
        return self.extract_question(request, question)

    def extract_question(
        self,
        request: BiMetricExtractionRequest,
        question: str,
    ) -> BiMetricExtractionResult:
        definition = METRIC_CATALOG[request.metric_id]
        if isinstance(definition, DerivedMetricDefinition):
            return self._invalid(request, definition.value_kind, "derived_metric_requires_calculation")

        if not isinstance(definition, SourceMetricDefinition):
            return self._invalid(request, definition.value_kind, "unsupported_metric_definition")

        context = self._retriever.retrieve(
            BiRetrievalRequest(extraction=request, question=question)
        )
        if not self._lineage_matches(request, context):
            return self._invalid(request, definition.value_kind, "retrieval_lineage_mismatch")

        reader_result = self._reader.read(request, context)
        match reader_result:
            case ReaderContractFailure(code=code):
                return self._invalid(request, definition.value_kind, code)
            case BiMetricReaderResponse() as response:
                return self._validate_response(request, definition.value_kind, context, response)
            case unreachable:
                assert_never(unreachable)

    @staticmethod
    def _lineage_matches(
        request: BiMetricExtractionRequest,
        context: BiRetrievedContext,
    ) -> bool:
        return (
            context.request_id == request.request_id
            and context.file_name == request.source.file_name
            and context.workbook_hash == request.source.workbook_hash
            and context.index_id == request.source.index_id
        )

    def _validate_response(
        self,
        request: BiMetricExtractionRequest,
        value_kind: ValueKind,
        context: BiRetrievedContext,
        response: BiMetricReaderResponse,
    ) -> BiMetricExtractionResult:
        metric_match = str(response.metric_id) == str(request.metric_id)
        period_match = (
            str(response.period_id) == str(request.period_id)
            or str(request.period_id).endswith(str(response.period_id))
            or str(response.period_id).endswith(str(request.period_id))
        )
        if not metric_match or not period_match:
            return self._invalid(request, value_kind, "reader_identity_mismatch")

        evidence = self._trusted_evidence(context, response.evidence_cell_ids)

        if response.status is MetricStatus.AVAILABLE:
            if self._is_missing_token(response.raw_value):
                return self._unavailable(
                    request,
                    value_kind,
                    MetricStatus.MISSING,
                    "source_value_missing",
                    raw_value=response.raw_value,
                    evidence=evidence,
                )
            if response.normalized_value is None:
                return self._invalid(request, value_kind, "available_value_missing")
            currency = response.currency
            scale = response.scale
            if value_kind is ValueKind.AMOUNT and (
                currency is None or scale is None
            ):
                profile = self._profiles.get_for_source(request.source)
                if profile is not None:
                    currency = currency or profile.currency
                    scale = scale or profile.scale
            if value_kind is ValueKind.AMOUNT and (
                currency is None or scale is None
            ):
                return self._unavailable(
                    request,
                    value_kind,
                    MetricStatus.AMBIGUOUS,
                    "amount_unit_ambiguous",
                    raw_value=response.raw_value,
                    evidence=evidence,
                )
            observation = AvailableObservation(
                period_id=request.period_id,
                status=MetricStatus.AVAILABLE,
                raw_value=response.raw_value,
                normalized_value=response.normalized_value,
                evidence=evidence,
                notes=response.notes,
            )
            return BiMetricExtractionResult(
                metric_id=request.metric_id,
                period_id=request.period_id,
                value_kind=value_kind,
                currency=currency,
                scale=scale,
                observation=observation,
            )

        if response.normalized_value is not None:
            return self._invalid(request, value_kind, "unavailable_value_present")
        return self._unavailable(
            request,
            value_kind,
            response.status,
            response.reason or f"reader_{response.status.value}",
            raw_value=response.raw_value,
            evidence=evidence,
            currency=response.currency,
            scale=response.scale,
            notes=response.notes,
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
    def _is_missing_token(raw_value: str | None) -> bool:
        if raw_value is None:
            return True
        return raw_value.strip().upper() in MISSING_TOKENS

    @staticmethod
    def _invalid(
        request: BiMetricExtractionRequest,
        value_kind: ValueKind,
        reason: str,
    ) -> BiMetricExtractionResult:
        return BiMetricExtractionService._unavailable(
            request,
            value_kind,
            MetricStatus.INVALID,
            reason,
        )

    @staticmethod
    def _unavailable(
        request: BiMetricExtractionRequest,
        value_kind: ValueKind,
        status: MetricStatus,
        reason: str,
        *,
        raw_value: str | None = None,
        evidence: tuple[BiEvidence, ...] = (),
        currency: str | None = None,
        scale: AmountScale | None = None,
        notes: tuple[str, ...] = (),
    ) -> BiMetricExtractionResult:
        if status is MetricStatus.AVAILABLE:
            raise BiMetricExtractionStatusError(status)
        unavailable_status = cast(
            Literal[
                MetricStatus.MISSING,
                MetricStatus.AMBIGUOUS,
                MetricStatus.INVALID,
                MetricStatus.NOT_MEANINGFUL,
            ],
            status,
        )
        observation = UnavailableObservation(
            period_id=request.period_id,
            status=unavailable_status,
            raw_value=raw_value,
            evidence=evidence,
            notes=notes,
            reason=reason,
        )
        return BiMetricExtractionResult(
            metric_id=request.metric_id,
            period_id=request.period_id,
            value_kind=value_kind,
            currency=currency,
            scale=scale,
            observation=observation,
        )
