from __future__ import annotations

from datetime import date

import polars as pl

from fair_value.datasets.asof import build_valuation_asof_dataset
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

MARKET_PATH = PROJECT_ROOT / "data" / "silver" / "market_price" / "canonical.parquet"
FUNDAMENTAL_PATH = PROJECT_ROOT / "data" / "gold" / "features" / "fundamental_features.parquet"
ECONOMIC_PATH = PROJECT_ROOT / "data" / "silver" / "economic_indicators" / "canonical.parquet"
DOMESTIC_CYCLE_PATH = (
    PROJECT_ROOT / "data" / "gold" / "features" / "semiconductor_cycle_features.parquet"
)
GLOBAL_CYCLE_PATH = (
    PROJECT_ROOT / "data" / "gold" / "features" / "global_semiconductor_cycle_features.parquet"
)
OUTPUT_PATH = PROJECT_ROOT / "data" / "gold" / "model_inputs" / "valuation_asof_monthly.parquet"


def build_asof_dataset(
    *,
    start_date: date = date(2015, 1, 1),
    end_date: date | None = None,
) -> pl.DataFrame:
    return build_valuation_asof_dataset(
        market_prices=pl.read_parquet(MARKET_PATH),
        fundamentals=pl.read_parquet(FUNDAMENTAL_PATH),
        economic_indicators=pl.read_parquet(ECONOMIC_PATH),
        domestic_cycle_features=pl.read_parquet(DOMESTIC_CYCLE_PATH),
        global_cycle_features=pl.read_parquet(GLOBAL_CYCLE_PATH),
        start_date=start_date,
        end_date=end_date,
    )


def main() -> None:
    frame = build_asof_dataset()
    path = write_parquet_atomic(frame, OUTPUT_PATH)
    print(f"row_count={frame.height}")
    print(
        frame.group_by("ticker")
        .agg(
            pl.len().alias("rows"),
            pl.col("valuation_date").min().alias("min_valuation_date"),
            pl.col("valuation_date").max().alias("max_valuation_date"),
            pl.col("financial_available_at").null_count().alias("financial_nulls"),
        )
        .sort("ticker")
    )
    print(f"schema={frame.schema}")
    print(f"output_path={path}")


if __name__ == "__main__":
    main()
