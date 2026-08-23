from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import cast

import polars as pl

COMMON_RESULT_COLUMNS = (
    "valuation_date",
    "ticker",
    "model_name",
    "model_version",
    "horizon_months",
    "market_price",
    "model_value",
    "value_to_price",
    "target_date",
    "future_trading_date",
    "future_price",
    "future_return",
    "fair_value_low",
    "fair_value_high",
    "future_price_within_range",
)


def combine_backtest_results(
    benchmark_results: pl.DataFrame,
    cycle_results: pl.DataFrame,
) -> pl.DataFrame:
    """Standardize benchmark and range-model evaluations for reporting only."""
    benchmark_required = {
        "valuation_date",
        "ticker",
        "model_name",
        "assumptions_version",
        "horizon_months",
        "market_price",
        "model_value",
        "value_to_price",
        "target_date",
        "future_trading_date",
        "future_price",
        "future_return",
    }
    cycle_required = {
        "valuation_date",
        "ticker",
        "model_name",
        "model_version",
        "horizon_months",
        "market_price",
        "model_value",
        "base_value_to_price",
        "target_date",
        "future_trading_date",
        "future_price",
        "future_return",
        "fair_value_low",
        "fair_value_high",
        "future_price_within_range",
    }
    _require_columns(benchmark_results, benchmark_required, "benchmark_results")
    _require_columns(cycle_results, cycle_required, "cycle_results")

    benchmark = benchmark_results.with_columns(
        pl.col("assumptions_version").alias("model_version"),
        pl.lit(None, dtype=pl.Float64).alias("fair_value_low"),
        pl.lit(None, dtype=pl.Float64).alias("fair_value_high"),
        pl.lit(None, dtype=pl.Boolean).alias("future_price_within_range"),
    ).select(COMMON_RESULT_COLUMNS)
    cycle = cycle_results.with_columns(
        pl.col("base_value_to_price").alias("value_to_price")
    ).select(COMMON_RESULT_COLUMNS)
    return (
        pl.concat([benchmark, cycle], how="vertical")
        .with_columns(pl.col("valuation_date").dt.year().alias("valuation_year"))
        .sort(["model_name", "ticker", "valuation_date", "horizon_months"])
    )


def select_non_overlapping_horizons(
    results: pl.DataFrame,
    *,
    series_columns: Sequence[str] = ("model_name", "ticker", "horizon_months"),
) -> pl.DataFrame:
    """Select sequential evaluation windows that do not overlap within each series."""
    if not series_columns:
        raise ValueError("series_columns must not be empty")
    required = {
        *series_columns,
        "valuation_date",
        "target_date",
        "future_trading_date",
    }
    _require_columns(results, required, "backtest_results")

    sort_columns = [*series_columns, "valuation_date"]
    ordered = results.sort(sort_columns).with_row_index("_report_row")
    selected_rows: list[int] = []
    last_boundary: dict[tuple[object, ...], date] = {}

    for row in ordered.select(
        "_report_row",
        *series_columns,
        "valuation_date",
        "target_date",
        "future_trading_date",
    ).iter_rows(named=True):
        key = tuple(row[column] for column in series_columns)
        valuation_date = cast(date, row["valuation_date"])
        previous_boundary = last_boundary.get(key)
        if previous_boundary is not None and valuation_date < previous_boundary:
            continue

        selected_rows.append(cast(int, row["_report_row"]))
        future_date = row["future_trading_date"]
        last_boundary[key] = (
            future_date if isinstance(future_date, date) else cast(date, row["target_date"])
        )

    return (
        ordered.filter(pl.col("_report_row").is_in(selected_rows))
        .drop("_report_row")
        .sort(sort_columns)
    )


def build_backtest_summary(
    results: pl.DataFrame,
    *,
    group_columns: Sequence[str],
) -> pl.DataFrame:
    """Aggregate evaluation diagnostics without treating realized price as intrinsic value."""
    required = {
        *group_columns,
        "future_return",
        "value_to_price",
        "model_value",
        "fair_value_low",
        "fair_value_high",
        "future_price_within_range",
    }
    _require_columns(results, required, "backtest_results")
    if not group_columns:
        raise ValueError("group_columns must not be empty")

    evaluated = pl.col("future_return").is_not_null()
    value_above_price = pl.col("value_to_price") >= 1.0
    range_width_ratio = (pl.col("fair_value_high") - pl.col("fair_value_low")) / pl.col(
        "model_value"
    ).abs()

    return (
        results.group_by(list(group_columns))
        .agg(
            pl.len().alias("rows"),
            evaluated.sum().alias("evaluated_rows"),
            pl.col("future_return").null_count().alias("pending_rows"),
            pl.col("future_return").mean().alias("mean_future_return"),
            pl.col("future_return").median().alias("median_future_return"),
            pl.corr("value_to_price", "future_return").alias("value_to_price_return_correlation"),
            (evaluated & value_above_price).sum().alias("evaluated_value_to_price_ge_1"),
            (evaluated & ~value_above_price).sum().alias("evaluated_value_to_price_lt_1"),
            pl.when(evaluated & value_above_price)
            .then(pl.col("future_return"))
            .otherwise(None)
            .median()
            .alias("median_return_value_to_price_ge_1"),
            pl.when(evaluated & ~value_above_price)
            .then(pl.col("future_return"))
            .otherwise(None)
            .median()
            .alias("median_return_value_to_price_lt_1"),
            pl.col("future_price_within_range").mean().alias("range_coverage"),
            range_width_ratio.mean().alias("mean_range_width_to_base"),
        )
        .with_columns(
            pl.col("value_to_price_return_correlation").fill_nan(None),
            pl.col("mean_range_width_to_base").fill_nan(None),
        )
        .sort(list(group_columns))
    )


def _require_columns(
    frame: pl.DataFrame,
    required: set[str],
    frame_name: str,
) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{frame_name} missing required columns: {sorted(missing)}")
