from datetime import date

import polars as pl
import pytest

from fair_value.quality.datasets import (
    validate_asof_dataset,
    validate_market_prices,
)


def _market_prices() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ticker": ["005930", "005930"],
            "trading_date": [date(2025, 1, 2), date(2025, 1, 3)],
            "open": [100, 109],
            "high": [105, 112],
            "low": [99, 108],
            "close": [100, 110],
            "volume": [1_000, 2_000],
            "daily_return": [None, 0.1],
            "source": ["kis", "kis"],
            "adjusted": [True, True],
        }
    )


def test_market_quality_accepts_canonical_adjusted_prices() -> None:
    report = validate_market_prices(_market_prices())

    report.assert_passed()
    assert report.error_count == 0


def test_market_quality_rejects_non_adjusted_or_wrong_return() -> None:
    invalid = _market_prices().with_columns(
        pl.Series("adjusted", [True, False]),
        pl.Series("daily_return", [None, 0.2]),
    )
    report = validate_market_prices(invalid)

    with pytest.raises(ValueError, match="quality gate failed"):
        report.assert_passed()
    assert report.error_count == 2


def test_asof_quality_rejects_future_availability() -> None:
    frame = pl.DataFrame(
        {
            "ticker": ["005930"],
            "valuation_date": [date(2025, 3, 31)],
            "market_price": [60_000.0],
            "financial_period_end": [date(2024, 12, 31)],
            "financial_available_at": [date(2025, 4, 1)],
        }
    )
    report = validate_asof_dataset(frame)

    with pytest.raises(ValueError, match="future_availability"):
        report.assert_passed()
