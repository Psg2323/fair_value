from datetime import date

from fair_value.jobs.trade_batch import (
    build_parser,
    month_periods,
    periods_by_year,
    subtract_months,
)


def test_month_periods_and_year_chunks_are_deterministic() -> None:
    periods = month_periods(date(2025, 11, 1), date(2026, 2, 28))

    assert periods == ["202511", "202512", "202601", "202602"]
    assert periods_by_year(periods) == [
        ["202511", "202512"],
        ["202601", "202602"],
    ]


def test_subtract_months_crosses_year_boundary() -> None:
    assert subtract_months(date(2026, 2, 28), 4) == date(2025, 10, 1)


def test_parser_accepts_one_trade_source() -> None:
    args = build_parser().parse_args(["--source", "un_comtrade"])

    assert args.source == "un_comtrade"
