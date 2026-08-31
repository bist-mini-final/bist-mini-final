from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from backend.domains.bi.application import BiApiServices, BiApplicationService
from backend.domains.bi.application.use_cases import (
    BiConflictError,
    BiNotFoundError,
)
from backend.domains.bi.domain.models import (
    BiMaterializationJob,
    BiMaterializationRequest,
    BiMaterializationSource,
    CompanyId,
    IndexId,
    JobId,
    MaterializationStatus,
)
from backend.domains.bi.domain.question_records import BiQuestionJobProgress

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return NOW


def _request(workbook_hash: str = "a" * 64) -> BiMaterializationRequest:
    return BiMaterializationRequest(
        company_id=CompanyId("amesoft"),
        display_name="AmeSoft",
        source=BiMaterializationSource(
            file_name="amesoft.xlsx",
            workbook_hash=workbook_hash,
            index_id=IndexId("idx-amesoft"),
        ),
    )


def _job(
    status: MaterializationStatus,
    workbook_hash: str = "a" * 64,
) -> BiMaterializationJob:
    return BiMaterializationJob(
        job_id=JobId("job-amesoft"),
        company_id=CompanyId("amesoft"),
        workbook_hash=workbook_hash,
        status=status,
        completed_requests=0,
        total_requests=0,
        started_at=NOW,
        updated_at=NOW,
    )


def _application(
    *,
    store: object,
    materializations: object | None = None,
    questions: object | None = None,
) -> BiApplicationService:
    return BiApplicationService(
        BiApiServices(
            store=cast(Any, store),
            materializations=cast(Any, materializations or store),
            questions=cast(Any, questions or SimpleNamespace()),
            clock=_Clock(),
        )
    )


def test_materialization_command_builds_and_enqueues_a_deterministic_job() -> None:
    store = SimpleNamespace(find_latest_job_async=AsyncMock(return_value=None))
    queue = SimpleNamespace(enqueue_async=AsyncMock(side_effect=lambda _request, job: job))
    application = _application(store=store, materializations=queue)

    accepted = asyncio.run(application.create_materialization(_request()))

    assert accepted.status is MaterializationStatus.QUEUED
    assert str(accepted.job_id).startswith("job-")
    queued = queue.enqueue_async.await_args.args[1]
    assert queued.company_id == CompanyId("amesoft")
    assert queued.workbook_hash == "a" * 64


def test_materialization_command_reuses_same_source_and_rejects_active_replacement() -> None:
    current = _job(MaterializationStatus.PROFILING)
    store = SimpleNamespace(find_latest_job_async=AsyncMock(return_value=current))
    queue = SimpleNamespace(enqueue_async=AsyncMock())
    application = _application(store=store, materializations=queue)

    accepted = asyncio.run(application.create_materialization(_request()))
    assert accepted.job_id == current.job_id
    queue.enqueue_async.assert_not_awaited()

    with pytest.raises(BiConflictError, match="materialization is active"):
        asyncio.run(application.create_materialization(_request("b" * 64)))


def test_dashboard_query_reports_missing_company_as_application_error() -> None:
    store = SimpleNamespace(
        get_company_async=AsyncMock(return_value=None),
        get_current_async=AsyncMock(return_value=None),
        get_latest_job_async=AsyncMock(return_value=None),
    )
    application = _application(store=store)

    with pytest.raises(BiNotFoundError, match="company not found"):
        asyncio.run(application.get_dashboard(CompanyId("missing")))


def test_materialization_stream_projection_includes_question_progress() -> None:
    job = _job(MaterializationStatus.MATERIALIZING)
    progress = BiQuestionJobProgress(
        job_id=job.job_id,
        total_questions=10,
        queued_questions=2,
        running_questions=1,
        completed_questions=6,
        failed_questions=1,
    )
    store = SimpleNamespace(get_job=Mock(return_value=job))
    questions = SimpleNamespace(get_job_progress=Mock(return_value=progress))
    application = _application(store=store, questions=questions)

    projected = application.load_materialization(str(job.job_id))

    assert projected.completed_requests == 7
    assert projected.total_requests == 10
    assert projected.message == "지표 질문 7/10건을 병렬 처리했습니다."
