from backend.bi.models import JobId
from backend.bi.question_batch import BiQuestionBatchPlan
from backend.bi.question_records import BiQuestionJobProgress


class UnusedQuestionApi:
    def queue_materialization_questions(
        self,
        plan: BiQuestionBatchPlan,
    ) -> BiQuestionJobProgress:
        raise AssertionError(f"question queue must not be called: {plan.job_id}")

    def get_job_progress(
        self,
        job_id: JobId,
    ) -> BiQuestionJobProgress | None:
        raise AssertionError(f"question progress must not be called: {job_id}")
