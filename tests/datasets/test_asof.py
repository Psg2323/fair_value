from datetime import date

import polars as pl

from fair_value.datasets.asof import (
    assert_point_in_time,
    build_monthly_valuation_calendar,
    build_valuation_asof_dataset,
)


def test_monthly_calendar_uses_last_available_trading_day() -> None:
    prices = pl.DataFrame(
        {
            "ticker": ["005930", "005930", "005930"],
            "trading_date": [
                date(2026, 1, 29),
                date(2026, 1, 30),
                date(2026, 2, 27),
            ],
            "close": [100, 101, 110],
        }
    )

    calendar = build_monthly_valuation_calendar(prices)

    assert calendar["valuation_date"].to_list() == [
        date(2026, 1, 30),
        date(2026, 2, 27),
    ]
    assert calendar["market_price"].to_list() == [101.0, 110.0]


def test_asof_dataset_excludes_future_and_late_older_financials() -> None:
    prices = pl.DataFrame(
        {
            "ticker": ["005930"] * 4,
            "trading_date": [
                date(2026, 1, 30),
                date(2026, 2, 27),
                date(2026, 3, 31),
                date(2026, 5, 29),
            ],
            "close": [100, 110, 120, 130],
        }
    )
    fundamentals = pl.DataFrame(
        {
            "ticker": ["005930", "005930", "005930"],
            "period_end": [
                date(2025, 12, 31),
                date(2024, 12, 31),
                date(2026, 3, 31),
            ],
            "available_at": [
                date(2026, 2, 15),
                date(2026, 3, 20),
                date(2026, 5, 15),
            ],
            "receipt_no": ["newer", "late_old", "future"],
            "source": ["opendart"] * 3,
            "equity_per_distributed_share": [90.0, 80.0, 100.0],
        }
    )
    indicators = _indicator_frame()
    domestic, global_cycle = _cycle_frames()

    result = build_valuation_asof_dataset(
        prices,
        fundamentals,
        indicators,
        domestic,
        global_cycle,
        indicator_ids=("korea_treasury_3y",),
    )

    assert result["valuation_date"].to_list() == [
        date(2026, 2, 27),
        date(2026, 3, 31),
        date(2026, 5, 29),
    ]
    assert result["financial_receipt_no"].to_list() == ["newer", "newer", "future"]
    assert result["indicator_korea_treasury_3y"].to_list() == [3.0, 3.0, 3.2]
    assert_point_in_time(result)


def _indicator_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "indicator_id": ["korea_treasury_3y", "korea_treasury_3y"],
            "period_end": [date(2026, 2, 20), date(2026, 4, 30)],
            "available_at": [date(2026, 2, 20), date(2026, 4, 30)],
            "value": [3.0, 3.2],
        }
    )


def _cycle_frames() -> tuple[pl.DataFrame, pl.DataFrame]:
    domestic = pl.DataFrame(
        {
            "period_end": [date(2026, 1, 31)],
            "available_at": [date(2026, 2, 20)],
            "semiconductor_production_yoy": [0.1],
        }
    )
    global_cycle = pl.DataFrame(
        {
            "period_end": [date(2026, 1, 31)],
            "available_at": [date(2026, 2, 18)],
            "us_semiconductor_industrial_production_yoy": [0.2],
        }
    )
    return domestic, global_cycle
