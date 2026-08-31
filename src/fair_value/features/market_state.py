from __future__ import annotations

import polars as pl

MARKET_STATE_COLUMNS = (
    "ticker",
    "trading_date",
    "minute_count",
    "open_price",
    "close_price",
    "high_price",
    "low_price",
    "total_volume",
    "vwap",
    "close_vwap_ratio",
    "realized_volatility",
    "opening_return_30m",
    "closing_return_30m",
    "opening_volume_ratio",
    "closing_volume_ratio",
    "max_1m_return",
    "min_1m_return",
    "volume_spike_count",
    "intraday_momentum",
    "intraday_reversal",
    "source",
)


def derive_daily_market_state(minute_prices: pl.DataFrame) -> pl.DataFrame:
    """Compress canonical minute prices to one explainable market-state row per day."""
    required = {"ticker", "trading_date", "timestamp", "price", "volume", "source"}
    if missing := required - set(minute_prices.columns):
        raise ValueError(f"Missing canonical minute-price columns: {sorted(missing)}")
    keys = ["ticker", "trading_date"]
    working = (
        minute_prices.sort([*keys, "timestamp"])
        .with_columns(
            (
                pl.col("timestamp").dt.hour().cast(pl.Int32) * 60
                + pl.col("timestamp").dt.minute().cast(pl.Int32)
            ).alias("_minute_of_day"),
            (
                pl.col("price").cast(pl.Float64).log()
                - pl.col("price").shift(1).over(keys).cast(pl.Float64).log()
            ).alias("_log_return"),
            (pl.col("price").cast(pl.Float64) * pl.col("volume")).alias("_turnover"),
            pl.col("volume").median().over(keys).alias("_median_volume"),
        )
        .with_columns(
            (pl.col("volume") > pl.col("_median_volume") * 3)
            .fill_null(False)
            .alias("_volume_spike")
        )
    )
    aggregated = working.group_by(keys, maintain_order=True).agg(
        pl.len().alias("minute_count"),
        pl.col("price").first().alias("open_price"),
        pl.col("price").last().alias("close_price"),
        pl.col("price").max().alias("high_price"),
        pl.col("price").min().alias("low_price"),
        pl.col("volume").sum().alias("total_volume"),
        pl.col("_turnover").sum().alias("_turnover"),
        pl.col("_log_return").pow(2).sum().sqrt().alias("realized_volatility"),
        pl.col("price").filter(pl.col("_minute_of_day") <= 570).last().alias("_opening_end_price"),
        pl.col("price")
        .filter(pl.col("_minute_of_day") >= 900)
        .first()
        .alias("_closing_start_price"),
        pl.col("volume").filter(pl.col("_minute_of_day") < 570).sum().alias("_opening_volume"),
        pl.col("volume").filter(pl.col("_minute_of_day") >= 900).sum().alias("_closing_volume"),
        pl.col("_log_return").max().alias("max_1m_return"),
        pl.col("_log_return").min().alias("min_1m_return"),
        pl.col("_volume_spike").sum().alias("volume_spike_count"),
        pl.col("source").first().alias("source"),
    )
    return (
        aggregated.with_columns(
            pl.when(pl.col("total_volume") > 0)
            .then(pl.col("_turnover") / pl.col("total_volume"))
            .otherwise(None)
            .alias("vwap"),
            (
                pl.col("_opening_end_price").cast(pl.Float64)
                / pl.col("open_price").cast(pl.Float64)
                - 1
            ).alias("opening_return_30m"),
            (
                pl.col("close_price").cast(pl.Float64)
                / pl.col("_closing_start_price").cast(pl.Float64)
                - 1
            ).alias("closing_return_30m"),
            pl.when(pl.col("total_volume") > 0)
            .then(pl.col("_opening_volume") / pl.col("total_volume"))
            .otherwise(None)
            .alias("opening_volume_ratio"),
            pl.when(pl.col("total_volume") > 0)
            .then(pl.col("_closing_volume") / pl.col("total_volume"))
            .otherwise(None)
            .alias("closing_volume_ratio"),
            (
                pl.col("close_price").cast(pl.Float64) / pl.col("open_price").cast(pl.Float64) - 1
            ).alias("intraday_momentum"),
            (
                pl.col("close_price").cast(pl.Float64) / pl.col("high_price").cast(pl.Float64) - 1
            ).alias("intraday_reversal"),
        )
        .with_columns(
            (pl.col("close_price").cast(pl.Float64) / pl.col("vwap") - 1).alias("close_vwap_ratio")
        )
        .select(MARKET_STATE_COLUMNS)
        .sort(keys)
    )
