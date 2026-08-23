from datetime import date

import polars as pl
import pytest

from fair_value.backtest.engine import (
    add_range_coverage,
    assert_future_only,
    evaluate_future_returns,
)


def test_evaluate_future_returns_uses_first_trading_day_on_or_after_target() -> None:
    valuations = pl.DataFrame(
        {
            "valuation_date": [date(2025, 1, 31)],
            "ticker": ["005930"],
            "model_name": ["book_value"],
            "market_price": [50_000.0],
            "model_value": [60_000.0],
        }
    )
    prices = pl.DataFrame(
        {
            "ticker": ["005930", "005930", "005930"],
            "trading_date": [
                date(2025, 1, 31),
                date(2025, 2, 28),
                date(2025, 3, 31),
            ],
            "close": [50_000.0, 55_000.0, 60_000.0],
        }
    )

    result = evaluate_future_returns(valuations, prices, horizons_months=(1, 2))

    one_month = result.filter(pl.col("horizon_months") == 1).row(0, named=True)
    two_month = result.filter(pl.col("horizon_months") == 2).row(0, named=True)
    assert one_month["target_date"] == date(2025, 2, 28)
    assert one_month["future_trading_date"] == date(2025, 2, 28)
    assert one_month["future_return"] == pytest.approx(0.10)
    assert two_month["future_return"] == pytest.approx(0.20)
    assert result.get_column("model_value").to_list() == [60_000.0, 60_000.0]


def test_unobserved_horizon_is_pending_not_dropped() -> None:
    valuations = pl.DataFrame(
        {
            "valuation_date": [date(2025, 3, 31)],
            "ticker": ["000660"],
            "market_price": [100_000.0],
            "model_value": [120_000.0],
        }
    )
    prices = pl.DataFrame(
        {
            "ticker": ["000660"],
            "trading_date": [date(2025, 3, 31)],
            "close": [100_000.0],
        }
    )

    result = evaluate_future_returns(valuations, prices, horizons_months=(1,))

    assert result.height == 1
    assert result.item(0, "future_price") is None
    assert result.item(0, "future_return") is None


def test_assert_future_only_rejects_pre_target_price() -> None:
    invalid = pl.DataFrame(
        {
            "valuation_date": [date(2025, 1, 31)],
            "target_date": [date(2025, 2, 28)],
            "future_trading_date": [date(2025, 2, 27)],
        }
    )

    with pytest.raises(ValueError, match="Look-ahead boundary violation"):
        assert_future_only(invalid)


def test_range_coverage_is_post_valuation_diagnostic() -> None:
    results = pl.DataFrame(
        {
            "future_price": [90.0, 120.0, None],
            "fair_value_low": [80.0, 80.0, 80.0],
            "fair_value_high": [100.0, 100.0, 100.0],
        }
    )

    covered = add_range_coverage(results)

    assert covered.get_column("future_price_within_range").to_list() == [
        True,
        False,
        None,
    ]
