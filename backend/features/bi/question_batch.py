from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from .catalog import (
    CATALOG_VERSION,
    METRIC_CATALOG,
    DerivedMetricDefinition,
    SourceMetricDefinition,
)
from .models import BiMaterializationRequest, BiPeriod, JobId, PeriodId
from .question_records import (
    BiQuestionBatch,
    BiQuestionRecord,
    BiQuestionStatus,
    QuestionId,
    QuestionVersion,
)


@dataclass(frozen=True, slots=True)
class BiQuestionBatchPlan:
    materialization: BiMaterializationRequest
    periods: tuple[BiPeriod, ...]
    job_id: JobId
    created_at: datetime
    question_version: QuestionVersion = field(
        default_factory=lambda: QuestionVersion(CATALOG_VERSION)
    )


def build_question_batch(plan: BiQuestionBatchPlan) -> BiQuestionBatch:
    questions: list[BiQuestionRecord] = []
    for definition in METRIC_CATALOG.values():
        match definition:
            case SourceMetricDefinition():
                for period in plan.periods:
                    persisted_period_id = (
                        period.period_id
                        if str(period.period_id).startswith(
                            f"{period.kind.value}-"
                        )
                        else PeriodId(
                            f"{period.kind.value}-{period.period_id}"
                        )
                    )
                    identity = "\x00".join(
                        (
                            str(plan.job_id),
                            str(plan.materialization.company_id),
                            plan.materialization.source.workbook_hash,
                            str(plan.materialization.source.index_id),
                            definition.metric_id.value,
                            str(persisted_period_id),
                            str(plan.question_version),
                        )
                    )
                    question_id = QuestionId(
                        "question-"
                        + sha256(identity.encode("utf-8")).hexdigest()[:24]
                    )
                    questions.append(
                        BiQuestionRecord(
                            question_id=question_id,
                            materialization_job_id=plan.job_id,
                            company_id=plan.materialization.company_id,
                            workbook_hash=plan.materialization.source.workbook_hash,
                            index_id=plan.materialization.source.index_id,
                            metric_id=definition.metric_id,
                            period_id=persisted_period_id,
                            question_version=plan.question_version,
                            question_text=definition.question_template.format(
                                period_label=period.label,
                                metric_label=definition.label_en,
                                metric_aliases=", ".join(definition.aliases_en),
                                statement_hint=" or ".join(definition.statement_hints),
                            ),
                            status=BiQuestionStatus.QUEUED,
                            attempt_count=0,
                            created_at=plan.created_at,
                            updated_at=plan.created_at,
                        )
                    )
            case DerivedMetricDefinition():
                continue
            case _:
                raise TypeError(
                    f"지원하지 않는 BI metric definition: {type(definition).__name__}"
                )
    return BiQuestionBatch(questions=tuple(questions))
