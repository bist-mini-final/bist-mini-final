import unittest

from backend.bi import database_schema
from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


class BiDatabaseSchemaTests(unittest.TestCase):
    def test_schema_defines_question_idempotency_and_one_answer_per_question(self) -> None:
        # Given / When
        schema = getattr(database_schema, "BI_SCHEMA_SQL")
        normalized = " ".join(schema.split())

        # Then
        self.assertIn("CREATE TABLE IF NOT EXISTS bi_questions", normalized)
        self.assertIn("CREATE TABLE IF NOT EXISTS bi_answers", normalized)
        self.assertIn("CREATE TABLE IF NOT EXISTS bi_document_profiles", normalized)
        self.assertIn(
            "UNIQUE (materialization_job_id, metric_id, period_id, question_version)",
            normalized,
        )
        self.assertIn("question_id VARCHAR(128) NOT NULL UNIQUE", normalized)

    def test_schema_keeps_missing_answers_as_null_instead_of_zero(self) -> None:
        # Given / When
        schema = getattr(database_schema, "BI_SCHEMA_SQL")
        normalized = " ".join(schema.split())

        # Then
        self.assertIn("answer_payload JSONB", normalized)
        self.assertNotIn("answer_payload JSONB NOT NULL", normalized)
        self.assertNotIn("normalized_value", normalized)

    def test_schema_constrains_question_and_answer_states(self) -> None:
        # Given / When
        schema = getattr(database_schema, "BI_SCHEMA_SQL")
        normalized = " ".join(schema.split())

        # Then
        self.assertIn(
            "status IN ('queued', 'running', 'completed', 'failed')",
            normalized,
        )
        self.assertIn("outcome IN ('completed', 'failed')", normalized)

    def test_schema_installer_creates_all_tables_idempotently(self) -> None:
        # Given
        installer = getattr(database_schema, "ensure_bi_schema")
        unavailable_error = getattr(
            database_schema,
            "BiDatabaseUnavailableError",
        )

        # When
        try:
            installer()
            installer()
        except unavailable_error as error:
            self.skipTest(str(error))

        # Then
        with get_pooled_raw_connection(PGVECTOR_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass('public.bi_questions'), "
                    "to_regclass('public.bi_answers'), "
                    "to_regclass('public.bi_document_profiles')"
                )
                tables = cursor.fetchone()
        self.assertEqual(
            tables,
            ("bi_questions", "bi_answers", "bi_document_profiles"),
        )


if __name__ == "__main__":
    unittest.main()
