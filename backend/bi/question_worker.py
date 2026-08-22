from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Final, Protocol, assert_never

from pydantic import ValidationError

from backend.providers.llm.chat_completion import ChatCompletionError
from modules.common.exceptions import ModuleExecutionError

from .extraction_models import BiMetricExtractionResult
from .models import AvailableObservation, UnavailableObservation
from .question_pipeline import BiQuestionSourceError
from .question_records import (
    AnswerId,
    BiAnswerRecord,
    BiCompletedAnswerRecord,
    BiFailedAnswerRecord,
    BiQuestionClaim,
    BiQuestionRecord,
    WorkflowRunId,
)
from .rag_adapter import RagPipelineContractError


BI_WORKER_MODEL: Final = "gpt-5.6-luna"
BiPipelineFailure = (
    ChatCompletionError
    | ModuleExecutionError
    | ValidationError
    | BiQuestionSourceError
    | RagPipelineContractError
)


class BiQuestionWorkerServicePort(Protocol):
    def claim_next(
        self,
        command: BiQuestionClaim,
    ) -> BiQuestionRecord | None: ...

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord: ...


class BiQuestionWorkerPipelinePort(Protocol):
    def execute(self, question: BiQuestionRecord) -> BiMetricExtractionResult: ...


class BiQuestionWorkerClockPort(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class SystemBiQuestionWorkerClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return perf_counter()


@dataclass(frozen=True, slots=True)
class BiQuestionExecutionTiming:
    created_at: datetime
    updated_at: datetime
    latency_ms: int


class BiQuestionWorker:
    def __init__(
        self,
        service: BiQuestionWorkerServicePort,
        pipeline: BiQuestionWorkerPipelinePort,
        clock: BiQuestionWorkerClockPort,
    ) -> None:
        self._service = service
        self._pipeline = pipeline
        self._clock = clock

    def run_one(
        self,
        worker_id: WorkflowRunId,
    ) -> BiQuestionRecord | None:
        claimed_at = self._clock.now()
        question = self._service.claim_next(
            BiQuestionClaim(
                workflow_run_id=worker_id,
                claimed_at=claimed_at,
            )
        )
        if question is None:
            return None

        started = self._clock.monotonic()
        try:
            result = self._pipeline.execute(question)
        except (
            ChatCompletionError,
            ModuleExecutionError,
            ValidationError,
            BiQuestionSourceError,
            RagPipelineContractError,
        ) as error:
            timing = self._timing(claimed_at, started)
            answer = self._failed_answer(question, error, timing)
        else:
            timing = self._timing(claimed_at, started)
            answer = self._completed_answer(question, result, timing)
        return self._service.save_answer(answer)

    def _completed_answer(
        self,
        question: BiQuestionRecord,
        result: BiMetricExtractionResult,
        timing: BiQuestionExecutionTiming,
    ) -> BiCompletedAnswerRecord:
        match result.observation:
            case AvailableObservation(
                raw_value=raw_value,
                normalized_value=normalized_value,
            ):
                answer_text = raw_value or str(normalized_value)
            case UnavailableObservation(raw_value=raw_value, reason=reason):
                answer_text = raw_value or reason
            case unreachable:
                assert_never(unreachable)
        return BiCompletedAnswerRecord(
            answer_id=self._answer_id(question),
            question_id=question.question_id,
            outcome="completed",
            answer_text=answer_text,
            result=result,
            evidence_cell_ids=tuple(
                evidence.cell_id for evidence in result.observation.evidence
            ),
            model_name=BI_WORKER_MODEL,
            latency_ms=timing.latency_ms,
            created_at=timing.created_at,
            updated_at=timing.updated_at,
        )

    def _failed_answer(
        self,
        question: BiQuestionRecord,
        error: BiPipelineFailure,
        timing: BiQuestionExecutionTiming,
    ) -> BiFailedAnswerRecord:
        match error:
            case RagPipelineContractError(code=code) | BiQuestionSourceError(
                code=code
            ):
                error_code = code
            case ChatCompletionError():
                error_code = "chat_completion_failed"
            case ModuleExecutionError():
                error_code = "pipeline_module_failed"
            case ValidationError():
                error_code = "pipeline_contract_invalid"
            case unreachable:
                assert_never(unreachable)
        message = str(error).strip() or type(error).__name__
        return BiFailedAnswerRecord(
            answer_id=self._answer_id(question),
            question_id=question.question_id,
            outcome="failed",
            error_code=error_code,
            error_message=message[:2_000],
            model_name=BI_WORKER_MODEL,
            latency_ms=timing.latency_ms,
            created_at=timing.created_at,
            updated_at=timing.updated_at,
        )

    def _timing(
        self,
        created_at: datetime,
        started: float,
    ) -> BiQuestionExecutionTiming:
        latency_ms = max(
            0,
            round((self._clock.monotonic() - started) * 1_000),
        )
        return BiQuestionExecutionTiming(
            created_at=created_at,
            updated_at=self._clock.now(),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _answer_id(question: BiQuestionRecord) -> AnswerId:
        digest = sha256(str(question.question_id).encode("utf-8")).hexdigest()
        return AnswerId("answer-" + digest[:24])
