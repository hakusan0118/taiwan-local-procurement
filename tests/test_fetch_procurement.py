import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "fetch_procurement.py"
)

SPEC = importlib.util.spec_from_file_location(
    "fetch_procurement",
    MODULE_PATH,
)

fetch_procurement = importlib.util.module_from_spec(
    SPEC
)

assert SPEC.loader is not None
SPEC.loader.exec_module(
    fetch_procurement
)


def test_regular_tender_name_stays_unchanged():
    record = {
        "date": 20130506,
        "unit_id": "3.76.55",
        "job_number": "ABC123",
        "filename": "source-a",
    }

    assert fetch_procurement.safe_name(
        record
    ) == (
        "20130506_3.76.55_ABC123.json"
    )


def test_case_variants_get_distinct_windows_safe_names():
    upper = {
        "date": 20130506,
        "unit_id": "3.76.55",
        "job_number": "SWC102040201",
        "filename": "source-a",
    }

    lower = {
        "date": 20130506,
        "unit_id": "3.76.55",
        "job_number": "swc102040201",
        "filename": "source-b",
    }

    upper_name = (
        fetch_procurement.safe_name(
            upper,
            disambiguate=True,
        )
    )

    lower_name = (
        fetch_procurement.safe_name(
            lower,
            disambiguate=True,
        )
    )

    assert (
        upper_name.casefold()
        != lower_name.casefold()
    )


def test_same_job_different_source_records_get_distinct_names():
    first = {
        "date": 20130506,
        "unit_id": "3.76.55",
        "job_number": "ABC123",
        "filename": "source-a",
    }

    second = {
        **first,
        "filename": "source-b",
    }

    first_name = (
        fetch_procurement.safe_name(
            first,
            disambiguate=True,
        )
    )

    second_name = (
        fetch_procurement.safe_name(
            second,
            disambiguate=True,
        )
    )

    assert first_name != second_name


def test_region_prefixes_are_separate():
    assert fetch_procurement.REGION_PREFIXES["hualien"] == "3.76.55"
    assert fetch_procurement.REGION_PREFIXES["taichung"] == "3.87"
    assert not fetch_procurement.is_in_scope("3.87.10", fetch_procurement.REGION_PREFIXES["hualien"])
    assert not fetch_procurement.is_in_scope("3.76.55.10", fetch_procurement.REGION_PREFIXES["taichung"])
