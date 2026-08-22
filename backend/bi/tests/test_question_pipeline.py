import unittest

from backend.bi.question_pipeline import BiQuestionPipeline
from backend.bi.models import BiMaterializationSource
from backend.bi.tests.test_question_service import queued_question


class RecordingExtractor:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    def extract_question(self, request, question: str):
        self.calls.append((request, question))
        return "metric-result"


class RecordingSourceResolver:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def resolve(self, question):
        self.calls.append(question)
        return BiMaterializationSource(
            file_name="company.xlsx",
            workbook_hash=question.workbook_hash,
            index_id=question.index_id,
        )


class BiQuestionPipelineTests(unittest.TestCase):
    def test_executes_the_persisted_question_against_its_index(self) -> None:
        # Given: a queued question contains the DB lineage required by retrieval.
        question = queued_question("job-task11", "question-task11")
        extractor = RecordingExtractor()
        source_resolver = RecordingSourceResolver()
        pipeline = BiQuestionPipeline(extractor, source_resolver)

        # When: the future question worker executes one question record.
        result = pipeline.execute(question)

        # Then: the stored question text and source lineage reach extraction unchanged.
        request, question_text = extractor.calls[0]
        self.assertEqual(result, "metric-result")
        self.assertEqual(question_text, question.question_text)
        self.assertEqual(request.request_id, question.question_id)
        self.assertEqual(request.metric_id, question.metric_id)
        self.assertEqual(request.period_id, question.period_id)
        self.assertEqual(request.source.index_id, question.index_id)
        self.assertEqual(request.source.workbook_hash, question.workbook_hash)
        self.assertEqual(source_resolver.calls, [question])


if __name__ == "__main__":
    unittest.main()
