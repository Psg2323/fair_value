from datetime import date

import polars as pl

from fair_value.backtest.report import (
    build_backtest_summary,
    combine_backtest_results,
    select_non_overlapping_horizons,
)


def _benchmark_results() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "valuation_date": [date(2025, 1, 31), date(2025, 2, 28)],
            "ticker": ["005930", "005930"],
            "model_name": ["book_value", "book_value"],
            "assumptions_version": ["v1", "v1"],
            "horizon_months": [3, 3],
            "market_price": [100.0, 110.0],
            "model_value": [120.0, 120.0],
            "value_to_price": [1.2, 120.0 / 110.0],
            "target_date": [date(2025, 4, 30), date(2025, 5, 28)],
            "future_trading_date": [date(2025, 4, 30), date(2025, 5, 28)],
            "future_price": [130.0, 125.0],
            "future_return": [0.3, 125.0 / 110.0 - 1.0],
        }
    )


def _cycle_results() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "valuation_date": [date(2025, 1, 31)],
            "ticker": ["005930"],
            "model_name": ["cycle_normalized_rim"],
            "model_version": ["research_v0"],
            "horizon_months": [3],
            "market_price": [100.0],
            "model_value": [110.0],
            "base_value_to_price": [1.1],
            "target_date": [date(2025, 4, 30)],
            "future_trading_date": [date(2025, 4, 30)],
            "future_price": [105.0],
            "future_return": [0.05],
            "fair_value_low": [90.0],
            "fair_value_high": [120.0],
            "future_price_within_range": [True],
        }
    )


def test_combine_results_standardizes_value_to_price_and_range_columns() -> None:
    result = combine_backtest_results(_benchmark_results(), _cycle_results())

    assert result.height == 3
    cycle = result.filter(pl.col("model_name") == "cycle_normalized_rim").row(
        0,
        named=True,
    )
    assert cycle["value_to_price"] == 1.1
    assert cycle["valuation_year"] == 2025
    benchmark = result.filter(pl.col("model_name") == "book_value")
    assert benchmark["fair_value_low"].null_count() == 2


def test_non_overlapping_selection_skips_windows_that_start_before_prior_end() -> None:
    combined = combine_backtest_results(_benchmark_results(), _cycle_results())
    selected = select_non_overlapping_horizons(combined)

    book_rows = selected.filter(pl.col("model_name") == "book_value")
    assert book_rows.height == 1
    assert book_rows.item(0, "valuation_date") == date(2025, 1, 31)


def test_summary_reports_range_coverage_only_for_range_model() -> None:
    combined = combine_backtest_results(_benchmark_results(), _cycle_results())
    summary = build_backtest_summary(
        combined,
        group_columns=("model_name", "ticker", "horizon_months"),
    )

    cycle = summary.filter(pl.col("model_name") == "cycle_normalized_rim").row(
        0,
        named=True,
    )
    book = summary.filter(pl.col("model_name") == "book_value").row(0, named=True)
    assert cycle["range_coverage"] == 1.0
    assert cycle["mean_range_width_to_base"] == (120.0 - 90.0) / 110.0
    assert book["range_coverage"] is None
