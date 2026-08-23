from __future__ import annotations

from collections.abc import Sequence

import polars as pl

DEFAULT_HORIZONS = (1, 3, 6, 12)


def evaluate_future_returns(
    valuations: pl.DataFrame,
    market_prices: pl.DataFrame,
    *,
    horizons_months: Sequence[int] = DEFAULT_HORIZONS,
) -> pl.DataFrame:
    """Attach forward returns after valuation without feeding them into model values."""
    valuation_required = {"valuation_date", "ticker", "market_price", "model_value"}
    missing_valuation = valuation_required - set(valuations.columns)
    if missing_valuation:
        raise ValueError(f"Missing valuation columns: {sorted(missing_valuation)}")

    price_required = {"ticker", "trading_date", "close"}
    missing_prices = price_required - set(market_prices.columns)
    if missing_prices:
        raise ValueError(f"Missing market-price columns: {sorted(missing_prices)}")

    horizons = tuple(horizons_months)
    if not horizons or any(months <= 0 for months in horizons):
        raise ValueError("horizons_months must contain positive integers")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons_months must not contain duplicates")

    future_prices = (
        market_prices.select(
            "ticker",
            pl.col("trading_date").alias("future_trading_date"),
            pl.col("close").cast(pl.Float64).alias("future_price"),
        )
        .filter(pl.col("future_price").is_not_null() & (pl.col("future_price") > 0))
        .sort(["ticker", "future_trading_date"])
    )
    frames: list[pl.DataFrame] = []
    for months in horizons:
        targets = valuations.with_columns(
            pl.col("valuation_date").dt.offset_by(f"{months}mo").alias("target_date"),
            pl.lit(months).cast(pl.Int16).alias("horizon_months"),
        )
        evaluated = targets.sort(["ticker", "target_date"]).join_asof(
            future_prices,
            left_on="target_date",
            right_on="future_trading_date",
            by="ticker",
            strategy="forward",
            check_sortedness=False,
        )
        frames.append(
            evaluated.with_columns(
                pl.when(pl.col("future_price").is_not_null())
                .then(pl.col("future_price") / pl.col("market_price") - 1.0)
                .otherwise(None)
                .alias("future_return")
            )
        )

    result = pl.concat(frames, how="vertical").sort(
        ["ticker", "valuation_date", "horizon_months", "model_name"]
        if "model_name" in valuations.columns
        else ["ticker", "valuation_date", "horizon_months"]
    )
    assert_future_only(result)
    return result


def add_range_coverage(
    results: pl.DataFrame,
    *,
    low_column: str = "fair_value_low",
    high_column: str = "fair_value_high",
) -> pl.DataFrame:
    """Add a diagnostic showing whether a realized future price falls in the range."""
    required = {"future_price", low_column, high_column}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"Missing range-evaluation columns: {sorted(missing)}")
    invalid_ranges = results.filter(
        pl.col(low_column).is_not_null()
        & pl.col(high_column).is_not_null()
        & (pl.col(low_column) > pl.col(high_column))
    )
    if invalid_ranges.height:
        raise ValueError(f"Invalid fair-value ranges in {invalid_ranges.height} rows")
    return results.with_columns(
        pl.when(pl.col("future_price").is_null())
        .then(None)
        .otherwise(
            pl.col("future_price").is_between(
                pl.col(low_column),
                pl.col(high_column),
                closed="both",
            )
        )
        .alias("future_price_within_range")
    )


def assert_future_only(results: pl.DataFrame) -> None:
    """Reject evaluation rows whose realized price predates their target horizon."""
    required = {"valuation_date", "target_date", "future_trading_date"}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"Missing future-evaluation columns: {sorted(missing)}")
    violations = results.filter(
        pl.col("future_trading_date").is_not_null()
        & (
            (pl.col("future_trading_date") < pl.col("target_date"))
            | (pl.col("future_trading_date") <= pl.col("valuation_date"))
        )
    )
    if violations.height:
        raise ValueError(f"Look-ahead boundary violation in {violations.height} rows")
