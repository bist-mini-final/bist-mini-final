"""Batch BI question worker: claims N questions, runs pipeline in parallel threads,
saves all answers in a single transaction.

Key design decisions
--------------------
* **ThreadPoolExecutor** - the existing RAG pipeline uses synchronous psycopg2
  and blocking OpenAI calls, so thread-level parallelism gives real concurrency
  without needing a full asyncio rewrite.
* **Embed-first grouping** - questions sharing the same workbook index_id also
  share the same embedding model/dimension, so we could further batch embed calls
  across questions.  The current ``FastRagPipelineAdapter`` already batches
  sub-queries within a single question; cross-question batching would require a
  deeper refactor of the embedder module and is left for a future iteration.
* **Heartbeat per question** - each claimed question gets its own heartbeat
  thread so the 180-second stale-window is respected even for large batches.
* **Best-effort save** - a failure in one question never aborts the others; each
  answer is saved independently after its pipeline completes.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Final, Protocol

from pydantic import ValidationError

from backend.domains.bi.application.errors import (
    BiProviderError,
    BiQuestionSourceError,
)
from backend.domains.bi.application.rag_errors import RagPipelineContractError
from backend.domains.bi.domain.extraction_models import BiMetricExtractionResult
from backend.domains.bi.domain.models import AvailableObservation, UnavailableObservation
from backend.domains.bi.domain.question_records import (
    AnswerId,
    BiAnswerOutcome,
    BiAnswerRecord,
    BiCompletedAnswerRecord,
    BiFailedAnswerRecord,
    BiQuestionClaim,
    BiQuestionRecord,
    QuestionId,
    WorkflowRunId,
)
from backend.shared.application.leases import (
    LeaseHeartbeat,
    terminate_process_on_lease_loss,
)
from backend.shared.application.workers import default_worker_id
from modules.common.exceptions import ModuleExecutionError

logger = logging.getLogger(__name__)

BI_BATCH_WORKER_MODEL: Final = "gpt-5.6-luna"

# Default number of questions a single pod processes per invocation.
DEFAULT_BATCH_SIZE: Final = 16

# Maximum parallel pipeline threads per pod.  Keep low enough to stay within
# the OpenAI TPM rate limit.  Can be tuned via BI_QUESTION_MAX_WORKERS env var.
DEFAULT_MAX_WORKERS: Final = 4

# Exception tuple for pipeline failures — must be a tuple (not a Union type)
# for use in ``except`` clauses.
_PIPELINE_FAILURE_TYPES = (
    BiProviderError,
    ModuleExecutionError,
    ValidationError,
    BiQuestionSourceError,
    RagPipelineContractError,
)


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class BiQuestionBatchServicePort(Protocol):
    def claim_next_batch(
        self,
        command: BiQuestionClaim,
        batch_size: int,
    ) -> tuple[BiQuestionRecord, ...]: ...

    def save_answer(self, answer: BiAnswerRecord) -> BiQuestionRecord: ...

    def heartbeat(
        self,
        question_id: QuestionId,
        workflow_run_id: WorkflowRunId,
    ) -> bool: ...


class BiQuestionBatchWorkerPipelinePort(Protocol):
    def execute(self, question: BiQuestionRecord) -> BiMetricExtractionResult: ...


class BiQuestionBatchWorkerClockPort(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class SystemBiQuestionBatchWorkerClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return perf_counter()


# ---------------------------------------------------------------------------
# Internal result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _QuestionOutcome:
    question: BiQuestionRecord
    answer: BiAnswerRecord


# ---------------------------------------------------------------------------
# Batch worker
# ---------------------------------------------------------------------------


class BiQuestionBatchWorker:
    """Processes a batch of BI questions in parallel threads.

    Each call to :meth:`run_batch` claims up to *batch_size* questions from the
    queue, fans them out to a thread pool, then saves every answer (success or
    failure) independently so a single flaky LLM call never blocks the rest.
    """

    def __init__(
        self,
        service: BiQuestionBatchServicePort,
        pipeline: BiQuestionBatchWorkerPipelinePort,
        clock: BiQuestionBatchWorkerClockPort,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_workers: int = DEFAULT_MAX_WORKERS,
    ) -> None:
        self._service = service
        self._pipeline = pipeline
        self._clock = clock
        self._batch_size = batch_size
        self._max_workers = max_workers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_batch(
        self,
        worker_id: WorkflowRunId,
    ) -> tuple[BiQuestionRecord, ...]:
        """Claim up to *batch_size* questions and process them in parallel.

        Returns the final :class:`BiQuestionRecord` objects (with updated
        ``status``) for all questions that were processed.  Returns an empty
        tuple when the queue is empty.
        """
        claimed_at = self._clock.now()
        questions = self._service.claim_next_batch(
            BiQuestionClaim(
                workflow_run_id=worker_id,
                claimed_at=claimed_at,
            ),
            batch_size=self._batch_size,
        )
        if not questions:
            return ()

        logger.info(
            "BiQuestionBatchWorker claimed %d questions (worker=%s)",
            len(questions),
            worker_id,
        )

        outcomes = self._run_parallel(questions, claimed_at)

        # Save answers sequentially - each save is a short DB round-trip and
        # keeping them out of the thread pool avoids connection pool contention.
        saved: list[BiQuestionRecord] = []
        for outcome in outcomes:
            try:
                saved_question = self._service.save_answer(outcome.answer)
                saved.append(saved_question)
            except Exception:
                logger.exception(
                    "Failed to save answer for question %s - it will be retried",
                    outcome.question.question_id,
                )

        logger.info(
            "BiQuestionBatchWorker saved %d/%d answers",
            len(saved),
            len(questions),
        )
        return tuple(saved)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_parallel(
        self,
        questions: tuple[BiQuestionRecord, ...],
        claimed_at: datetime,
    ) -> list[_QuestionOutcome]:
        """Execute all questions in a thread pool, each with its own heartbeat."""
        future_to_question: dict[Future[_QuestionOutcome], BiQuestionRecord] = {}

        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(questions)),
            thread_name_prefix="bi-batch",
        ) as executor:
            for question in questions:
                future = executor.submit(
                    self._execute_one,
                    question,
                    claimed_at,
                )
                future_to_question[future] = question

            outcomes: list[_QuestionOutcome] = []
            for future in as_completed(future_to_question):
                question = future_to_question[future]
                try:
                    outcomes.append(future.result())
                except Exception:
                    # Unexpected error not caught inside _execute_one; treat as
                    # failed so the question can be retried.
                    logger.exception(
                        "Unexpected error processing question %s",
                        question.question_id,
                    )
                    outcomes.append(
                        _QuestionOutcome(
                            question=question,
                            answer=self._failed_answer(
                                question,
                                RuntimeError("unexpected_worker_crash"),
                                self._timing(claimed_at, self._clock.monotonic()),
                            ),
                        )
                    )

        return outcomes

    def _execute_one(
        self,
        question: BiQuestionRecord,
        claimed_at: datetime,
    ) -> _QuestionOutcome:
        """Run the full RAG pipeline for a single question inside a thread."""
        workflow_run_id = question.workflow_run_id
        if workflow_run_id is None:
            raise RuntimeError("claimed BI question has no workflow_run_id")

        heartbeat = LeaseHeartbeat(
            lambda: self._service.heartbeat(
                question.question_id,
                workflow_run_id,
            ),
            interval_seconds=30,
            thread_name=f"bi-hb-{question.question_id}",
            logger=logger,
            failure_message=(
                f"BI question heartbeat failed (question_id={question.question_id})"
            ),
            on_lease_lost=terminate_process_on_lease_loss,
        )
        heartbeat.start()

        started = self._clock.monotonic()
        try:
            try:
                result = self._pipeline.execute(question)
            except _PIPELINE_FAILURE_TYPES as error:
                timing = self._timing(claimed_at, started)
                answer: BiAnswerRecord = self._failed_answer(question, error, timing)
            else:
                timing = self._timing(claimed_at, started)
                answer = self._completed_answer(question, result, timing)
            heartbeat.raise_if_lost()
        finally:
            heartbeat.stop()

        return _QuestionOutcome(question=question, answer=answer)

    # ------------------------------------------------------------------
    # Answer builders  (mirrored from BiQuestionWorker)
    # ------------------------------------------------------------------

    def _completed_answer(
        self,
        question: BiQuestionRecord,
        result: BiMetricExtractionResult,
        timing: _BiQuestionExecutionTiming,
    ) -> BiCompletedAnswerRecord:
        match result.observation:
            case AvailableObservation(raw_value=raw_value, normalized_value=normalized_value):
                answer_text = raw_value or str(normalized_value)
            case UnavailableObservation(raw_value=raw_value, reason=reason):
                answer_text = raw_value or reason
        return BiCompletedAnswerRecord(
            answer_id=self._answer_id(question),
            question_id=question.question_id,
            workflow_run_id=self._workflow_run_id(question),
            outcome=BiAnswerOutcome.COMPLETED,
            answer_text=answer_text,
            result=result,
            evidence_cell_ids=tuple(
                evidence.cell_id for evidence in result.observation.evidence
            ),
            model_name=BI_BATCH_WORKER_MODEL,
            latency_ms=timing.latency_ms,
            created_at=timing.created_at,
            updated_at=timing.updated_at,
        )

    def _failed_answer(
        self,
        question: BiQuestionRecord,
        error: Exception,
        timing: _BiQuestionExecutionTiming,
    ) -> BiFailedAnswerRecord:
        match error:
            case RagPipelineContractError(code=code) | BiQuestionSourceError(code=code):
                error_code = code
            case BiProviderError():
                error_code = "openai_response_failed"
            case ModuleExecutionError():
                error_code = "pipeline_module_failed"
            case ValidationError():
                error_code = "pipeline_contract_invalid"
            case _:
                error_code = "unexpected_worker_error"
        message = str(error).strip() or type(error).__name__
        return BiFailedAnswerRecord(
            answer_id=self._answer_id(question),
            question_id=question.question_id,
            workflow_run_id=self._workflow_run_id(question),
            outcome=BiAnswerOutcome.FAILED,
            error_code=error_code,
            error_message=message[:2_000],
            model_name=BI_BATCH_WORKER_MODEL,
            latency_ms=timing.latency_ms,
            created_at=timing.created_at,
            updated_at=timing.updated_at,
        )

    def _timing(
        self,
        created_at: datetime,
        started: float,
    ) -> _BiQuestionExecutionTiming:
        latency_ms = max(0, round((self._clock.monotonic() - started) * 1_000))
        return _BiQuestionExecutionTiming(
            created_at=created_at,
            updated_at=self._clock.now(),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _answer_id(question: BiQuestionRecord) -> AnswerId:
        digest = sha256(str(question.question_id).encode("utf-8")).hexdigest()
        return AnswerId("answer-" + digest[:24])

    @staticmethod
    def _workflow_run_id(question: BiQuestionRecord) -> WorkflowRunId:
        if question.workflow_run_id is None:
            raise RuntimeError("claimed BI question has no workflow_run_id")
        return question.workflow_run_id


# ---------------------------------------------------------------------------
# Timing helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _BiQuestionExecutionTiming:
    created_at: datetime
    updated_at: datetime
    latency_ms: int


def main(
    *,
    worker: BiQuestionBatchWorker,
    worker_id: WorkflowRunId | None = None,
) -> int:
    resolved_worker_id = worker_id or WorkflowRunId(default_worker_id())
    saved = worker.run_batch(resolved_worker_id)
    if not saved:
        print("BI question queue empty")
    else:
        statuses = ", ".join(question.status.value for question in saved)
        print(f"BI question batch of {len(saved)} finished [{statuses}]")
    return 0


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_WORKERS",
    "BiQuestionBatchWorker",
    "BiQuestionBatchServicePort",
    "BiQuestionBatchWorkerPipelinePort",
    "BiQuestionBatchWorkerClockPort",
    "SystemBiQuestionBatchWorkerClock",
    "main",
]
