from __future__ import annotations

import polars as pl

from fair_value.backtest.engine import add_range_coverage, evaluate_future_returns
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

RANGE_PATH = PROJECT_ROOT / "data" / "gold" / "valuation" / "fair_value_range.parquet"
MARKET_PATH = PROJECT_ROOT / "data" / "silver" / "market_price" / "canonical.parquet"
OUTPUT_PATH = PROJECT_ROOT / "data" / "gold" / "backtest" / "cycle_rim_future_returns.parquet"


def run_cycle_rim_backtest() -> pl.DataFrame:
    ranges = pl.read_parquet(RANGE_PATH).with_columns(
        pl.lit("cycle_normalized_rim").alias("model_name"),
        pl.col("fair_value_base").alias("model_value"),
    )
    future_returns = evaluate_future_returns(
        valuations=ranges,
        market_prices=pl.read_parquet(MARKET_PATH),
    )
    return add_range_coverage(future_returns)


def main() -> None:
    frame = run_cycle_rim_backtest()
    path = write_parquet_atomic(frame, OUTPUT_PATH)
    print(f"row_count={frame.height}")
    print(
        frame.group_by("horizon_months")
        .agg(
            pl.len().alias("rows"),
            pl.col("future_return").is_not_null().sum().alias("evaluated_rows"),
            pl.col("future_return").null_count().alias("pending_rows"),
            pl.col("future_return").median().alias("median_future_return"),
            pl.col("future_price_within_range").mean().alias("range_coverage"),
            pl.corr("base_value_to_price", "future_return").alias(
                "value_to_price_return_correlation"
            ),
        )
        .sort("horizon_months")
    )
    print(f"schema={frame.schema}")
    print(f"output_path={path}")


if __name__ == "__main__":
    main()
