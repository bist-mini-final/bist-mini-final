from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .catalog import METRIC_CATALOG, SourceMetricDefinition
from .extraction_models import BiMetricExtractionResult
from .materialization_models import BiDocumentProfile, BiSnapshotBuildInput
from .models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationRequest,
    BiPeriod,
    CompanyId,
    MetricStatus,
    UnavailableObservation,
)
from .question_pipeline import BiQuestionSourceResolverPort
from .question_records import BiQuestionRecord
from .question_snapshot import BiQuestionSnapshotDataError
from .snapshot_builder import BiSnapshotBuilder


@dataclass(frozen=True, slots=True)
class BiPersistedAnswerBatch:
    questions: tuple[BiQuestionRecord, ...]
    results: tuple[BiMetricExtractionResult, ...]


class BiInitialSnapshotAnswerPort(Protocol):
    def latest_batch(
        self,
        company_id: CompanyId,
        workbook_hash: str,
    ) -> BiPersistedAnswerBatch | None: ...


class BiInitialSnapshotStorePort(Protocol):
    def publish(self, snapshot: BiDashboardSnapshot) -> None: ...


class BiInitialSnapshotProfilePort(Protocol):
    def get(
        self,
        request: BiMaterializationRequest,
    ) -> BiDocumentProfile | None: ...


class BiInitialSnapshotClockPort(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class BiInitialSnapshotServices:
    answers: BiInitialSnapshotAnswerPort
    source_resolver: BiQuestionSourceResolverPort
    profiles: BiInitialSnapshotProfilePort
    store: BiInitialSnapshotStorePort
    clock: BiInitialSnapshotClockPort


class BiInitialSnapshotMaterializer:
    def __init__(self, services: BiInitialSnapshotServices) -> None:
        self._services = services

    def materialize(
        self,
        company: BiCompany,
        workbook_hash: str,
    ) -> BiDashboardSnapshot | None:
        batch = self._services.answers.latest_batch(
            company.company_id,
            workbook_hash,
        )
        if batch is None or not batch.results:
            return None
        first = batch.questions[0]
        if any(
            question.company_id != company.company_id
            or question.workbook_hash != workbook_hash
            or question.index_id != first.index_id
            or question.materialization_job_id != first.materialization_job_id
            for question in batch.questions
        ):
            raise BiQuestionSnapshotDataError("persisted answer lineage is mixed")
        materialization = BiMaterializationRequest(
            company_id=company.company_id,
            display_name=company.display_name,
            source=self._services.source_resolver.resolve(first),
        )
        profile = self._services.profiles.get(materialization)
        if profile is None:
            return None
        question_periods = {question.period_id for question in batch.questions}
        if question_periods != {period.period_id for period in profile.periods}:
            raise BiQuestionSnapshotDataError(
                "persisted questions do not match the document profile periods"
            )
        snapshot = BiSnapshotBuilder().build(
            BiSnapshotBuildInput(
                request=materialization,
                job_id=first.materialization_job_id,
                profile=profile,
                extracted=_complete_results(profile.periods, batch.results),
                generated_at=self._services.clock.now(),
            )
        )
        self._services.store.publish(snapshot)
        return snapshot


def _complete_results(
    periods: tuple[BiPeriod, ...],
    completed: tuple[BiMetricExtractionResult, ...],
) -> tuple[BiMetricExtractionResult, ...]:
    by_identity = {
        (result.metric_id, result.period_id): result for result in completed
    }
    return tuple(
        by_identity.get((metric_id, period.period_id))
        or BiMetricExtractionResult(
            metric_id=metric_id,
            period_id=period.period_id,
            value_kind=definition.value_kind,
            currency=None,
            scale=None,
            observation=UnavailableObservation(
                period_id=period.period_id,
                status=MetricStatus.MISSING,
                reason="answer_missing",
            ),
        )
        for metric_id, definition in METRIC_CATALOG.items()
        if isinstance(definition, SourceMetricDefinition)
        for period in periods
    )
