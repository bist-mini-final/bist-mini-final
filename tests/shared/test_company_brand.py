from backend.shared.domain.company_brand import (
    BRAND_ICON_CATALOG_VERSION,
    BRAND_ICON_SLUGS,
    assign_company_brand_mark,
)


def test_brand_catalog_has_one_hundred_unique_sources() -> None:
    assert len(BRAND_ICON_SLUGS) == 100
    assert len(set(BRAND_ICON_SLUGS)) == 100


def test_brand_assignment_is_stable_and_constrained() -> None:
    mark = assign_company_brand_mark("company-nexora", "a" * 64)

    assert assign_company_brand_mark("company-nexora", "a" * 64) == mark
    assert mark.catalog_version == BRAND_ICON_CATALOG_VERSION
    assert mark.source_icon in BRAND_ICON_SLUGS
    assert 0 <= mark.color_index < 12
    assert -12 <= mark.rotation_degrees <= 12
