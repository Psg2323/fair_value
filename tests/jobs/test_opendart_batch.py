import pytest

from fair_value.jobs.opendart_batch import resolve_year_range


def test_incremental_opendart_refreshes_recent_two_business_years() -> None:
    assert resolve_year_range("incremental", None, None, 2026) == (2025, 2026)


def test_historical_opendart_starts_from_project_baseline() -> None:
    assert resolve_year_range("historical", None, None, 2026) == (2015, 2026)


def test_explicit_opendart_years_override_mode_defaults() -> None:
    assert resolve_year_range("incremental", 2020, 2024, 2026) == (2020, 2024)


def test_opendart_year_range_rejects_reverse_order() -> None:
    with pytest.raises(ValueError, match="start_year"):
        resolve_year_range("historical", 2027, 2026, 2026)
