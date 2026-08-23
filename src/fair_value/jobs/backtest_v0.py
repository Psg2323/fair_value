from __future__ import annotations

import polars as pl

from fair_value.backtest.engine import evaluate_future_returns
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

VALUATION_PATH = PROJECT_ROOT / "data" / "gold" / "valuation" / "benchmark_valuations.parquet"
MARKET_PATH = PROJECT_ROOT / "data" / "silver" / "market_price" / "canonical.parquet"
OUTPUT_PATH = PROJECT_ROOT / "data" / "gold" / "backtest" / "benchmark_future_returns.parquet"


def run_backtest_v0() -> pl.DataFrame:
    return evaluate_future_returns(
        valuations=pl.read_parquet(VALUATION_PATH),
        market_prices=pl.read_parquet(MARKET_PATH),
    )


def main() -> None:
    frame = run_backtest_v0()
    path = write_parquet_atomic(frame, OUTPUT_PATH)
    print(f"row_count={frame.height}")
    print(
        frame.group_by(["model_name", "horizon_months"])
        .agg(
            pl.len().alias("rows"),
            pl.col("future_return").is_not_null().sum().alias("evaluated_rows"),
            pl.col("future_return").null_count().alias("pending_rows"),
            pl.col("future_return").median().alias("median_future_return"),
        )
        .sort(["model_name", "horizon_months"])
    )
    print(f"schema={frame.schema}")
    print(f"output_path={path}")


if __name__ == "__main__":
    main()
