from __future__ import annotations

from datetime import date

import polars as pl


def assign_fixed_assumption_walk_forward_folds(
    results: pl.DataFrame,
    *,
    initial_training_years: int,
) -> pl.DataFrame:
    """Create expanding annual folds while keeping all model assumptions fixed."""
    if initial_training_years < 1:
        raise ValueError("initial_training_years must be positive")
    if "valuation_date" not in results.columns:
        raise ValueError("walk-forward results require valuation_date")
    if results.is_empty():
        raise ValueError("walk-forward results must not be empty")

    minimum_year = results.select(pl.col("valuation_date").dt.year().min()).item()
    maximum_year = results.select(pl.col("valuation_date").dt.year().max()).item()
    if not isinstance(minimum_year, int) or not isinstance(maximum_year, int):
        raise ValueError("valuation_date must contain valid dates")

    first_test_year = minimum_year + initial_training_years
    frames: list[pl.DataFrame] = []
    for test_year in range(first_test_year, maximum_year + 1):
        test_rows = results.filter(pl.col("valuation_date").dt.year() == test_year)
        if test_rows.is_empty():
            continue
        frames.append(
            test_rows.with_columns(
                pl.lit(date(minimum_year, 1, 1)).alias("training_start_date"),
                pl.lit(date(test_year - 1, 12, 31)).alias("training_end_date"),
                pl.lit(date(test_year, 1, 1)).alias("test_start_date"),
                pl.lit(date(test_year, 12, 31)).alias("test_end_date"),
                pl.lit(test_year).cast(pl.Int32).alias("test_year"),
                pl.lit("fixed_assumptions_no_selection").alias("walk_forward_method"),
            )
        )

    if not frames:
        raise ValueError("No walk-forward test folds remain after the training window")
    return pl.concat(frames, how="vertical").sort(["test_year", "valuation_date"])
