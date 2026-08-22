from types import MappingProxyType
import unittest

from backend.bi.catalog import (
    CATALOG_VERSION,
    FORMULA_VERSION,
    METRIC_CATALOG,
    DerivedMetricDefinition,
    FallbackMetricDefinition,
    SourceMetricDefinition,
)
from backend.bi.models import MetricId


class MetricCatalogTests(unittest.TestCase):
    def test_catalog_contains_every_metric_id_once(self) -> None:
        # Given / When
        catalog_ids = set(METRIC_CATALOG)

        # Then
        self.assertEqual(catalog_ids, set(MetricId))

    def test_catalog_contains_eighteen_metrics(self) -> None:
        # Given / When / Then
        self.assertEqual(len(METRIC_CATALOG), 18)

    def test_catalog_versions_are_explicit(self) -> None:
        # Given / When / Then
        self.assertEqual((CATALOG_VERSION, FORMULA_VERSION), ("1", "1"))

    def test_source_metrics_define_machine_consumed_question_tokens(self) -> None:
        # Given
        source_definitions = (
            definition
            for definition in METRIC_CATALOG.values()
            if isinstance(definition, (SourceMetricDefinition, FallbackMetricDefinition))
        )

        # When
        templates = tuple(definition.question_template for definition in source_definitions)

        # Then
        self.assertTrue(all("{period_label}" in template for template in templates))
        self.assertTrue(all("{metric_label}" in template for template in templates))

    def test_derived_metrics_declare_formula_dependencies(self) -> None:
        # Given
        derived_definitions = (
            definition
            for definition in METRIC_CATALOG.values()
            if isinstance(definition, DerivedMetricDefinition)
        )

        # When
        dependency_counts = tuple(len(definition.dependencies) for definition in derived_definitions)

        # Then
        self.assertTrue(all(count > 0 for count in dependency_counts))

    def test_total_debt_prefers_direct_value_and_defines_fallback(self) -> None:
        # Given / When
        definition = METRIC_CATALOG[MetricId.TOTAL_DEBT]

        # Then
        self.assertIsInstance(definition, FallbackMetricDefinition)
        self.assertEqual(
            definition.dependencies,
            (
                MetricId.SHORT_TERM_DEBT,
                MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT,
                MetricId.LONG_TERM_DEBT,
            ),
        )

    def test_catalog_mapping_is_read_only(self) -> None:
        # Given / When / Then
        self.assertIsInstance(METRIC_CATALOG, MappingProxyType)


if __name__ == "__main__":
    unittest.main()
