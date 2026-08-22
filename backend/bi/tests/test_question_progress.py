import unittest

from backend.bi import question_records, question_service
from backend.bi.models import JobId
from backend.bi.tests.test_question_service import NOW, queued_question


class BiQuestionProgressTests(unittest.TestCase):
    def test_summarizes_every_question_status_for_one_job(self) -> None:
        # Given: one refresh job contains questions in every worker state.
        questions = (
            queued_question("job-task14", "question-task14-queued"),
            queued_question(
                "job-task14",
                "question-task14-running",
            ).model_copy(update={"status": "running"}),
            queued_question(
                "job-task14",
                "question-task14-completed-1",
            ).model_copy(update={"status": "completed"}),
            queued_question(
                "job-task14",
                "question-task14-completed-2",
            ).model_copy(update={"status": "completed"}),
            queued_question(
                "job-task14",
                "question-task14-failed",
            ).model_copy(update={"status": "failed"}),
        )
        summarize = getattr(question_service, "summarize_questions")

        # When: the API progress projection is built.
        progress = summarize(JobId("job-task14"), questions)

        # Then: total, queued, running, completed, and failed counts agree.
        self.assertEqual(progress.total_questions, 5)
        self.assertEqual(progress.queued_questions, 1)
        self.assertEqual(progress.running_questions, 1)
        self.assertEqual(progress.completed_questions, 2)
        self.assertEqual(progress.failed_questions, 1)

    def test_rejects_progress_whose_status_counts_do_not_match_total(self) -> None:
        # Given: an API boundary receives inconsistent aggregate counts.
        progress_type = getattr(question_records, "BiQuestionJobProgress")

        # When: the invalid progress model is parsed.
        with self.assertRaises(ValueError) as raised:
            progress_type(
                job_id="job-task14-invalid",
                total_questions=2,
                queued_questions=1,
                running_questions=0,
                completed_questions=0,
                failed_questions=0,
            )

        # Then: the aggregate cannot cross the typed boundary.
        self.assertEqual(
            raised.exception.errors()[0]["type"],
            "question_progress_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
