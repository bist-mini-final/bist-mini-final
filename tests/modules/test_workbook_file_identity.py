from backend.shared.application.workbook_identity import workbook_file_identity


def test_numbered_key_stats_filename_is_authoritative_company_identity() -> None:
    identity = workbook_file_identity("SPG_Company_KeyStats_09_meridian_logic.xlsm")

    assert identity is not None
    assert identity.company_name == "Meridian Logic"
    assert identity.ticker == ""


def test_rank_recalibrated_suffix_is_not_part_of_company_name() -> None:
    identity = workbook_file_identity(
        "SPG_Company_KeyStats_02_nexora_labs_rank_recalibrated.xlsx"
    )

    assert identity is not None
    assert identity.company_name == "Nexora Labs"


def test_unrecognized_filename_does_not_override_workbook_identity() -> None:
    assert workbook_file_identity("financial_report.xlsx") is None
