from __future__ import annotations

import polars as pl

SNAPSHOT_COLUMNS = (
    "ticker",
    "trading_date",
    "close_price",
    "vwap",
    "close_vwap_ratio",
    "realized_volatility",
    "valuation_date",
    "fair_value_low",
    "fair_value_base",
    "fair_value_high",
    "gap_to_fair_value_base",
    "price_position_in_range",
    "range_status",
)


def attach_valuation_gap(
    market_state: pl.DataFrame,
    fair_value_ranges: pl.DataFrame,
) -> pl.DataFrame:
    """Attach only fair values known on or before each market date."""
    market_required = {
        "ticker",
        "trading_date",
        "close_price",
        "vwap",
        "close_vwap_ratio",
        "realized_volatility",
    }
    value_required = {
        "ticker",
        "valuation_date",
        "fair_value_low",
        "fair_value_base",
        "fair_value_high",
    }
    if missing := market_required - set(market_state.columns):
        raise ValueError(f"Missing market-state columns: {sorted(missing)}")
    if missing := value_required - set(fair_value_ranges.columns):
        raise ValueError(f"Missing fair-value columns: {sorted(missing)}")

    joined = market_state.sort(["ticker", "trading_date"]).join_asof(
        fair_value_ranges.select(value_required).sort(["ticker", "valuation_date"]),
        left_on="trading_date",
        right_on="valuation_date",
        by="ticker",
        strategy="backward",
        check_sortedness=False,
    )
    return (
        joined.with_columns(
            pl.when(pl.col("fair_value_base").is_not_null() & (pl.col("close_price") > 0))
            .then(pl.col("fair_value_base") / pl.col("close_price").cast(pl.Float64) - 1)
            .otherwise(None)
            .alias("gap_to_fair_value_base"),
            pl.when(
                pl.col("fair_value_low").is_not_null()
                & (pl.col("fair_value_high") > pl.col("fair_value_low"))
            )
            .then(
                (pl.col("close_price") - pl.col("fair_value_low"))
                / (pl.col("fair_value_high") - pl.col("fair_value_low"))
            )
            .otherwise(None)
            .alias("price_position_in_range"),
            pl.when(pl.col("fair_value_low").is_null())
            .then(pl.lit("unavailable"))
            .when(pl.col("close_price") < pl.col("fair_value_low"))
            .then(pl.lit("below"))
            .when(pl.col("close_price") > pl.col("fair_value_high"))
            .then(pl.lit("above"))
            .otherwise(pl.lit("within"))
            .alias("range_status"),
        )
        .select(SNAPSHOT_COLUMNS)
        .sort(["ticker", "trading_date"])
    )
