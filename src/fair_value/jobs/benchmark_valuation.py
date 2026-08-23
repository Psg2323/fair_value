from __future__ import annotations

import polars as pl

from fair_value.config_loader import load_valuation
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic
from fair_value.valuation.benchmarks import (
    BenchmarkAssumptions,
    build_benchmark_valuations,
)

INPUT_PATH = PROJECT_ROOT / "data" / "gold" / "model_inputs" / "valuation_asof_monthly.parquet"
OUTPUT_PATH = PROJECT_ROOT / "data" / "gold" / "valuation" / "benchmark_valuations.parquet"


def run_benchmark_valuation() -> pl.DataFrame:
    config = load_valuation()
    cost = config.cost_of_equity
    assumptions = BenchmarkAssumptions(
        version=config.assumptions_version,
        risk_free_rate_scale=cost.risk_free_rate_scale,
        equity_risk_premium=cost.equity_risk_premium,
        beta=cost.beta,
        minimum_cost_of_equity=cost.minimum,
        maximum_cost_of_equity=cost.maximum,
    )
    return build_benchmark_valuations(
        pl.read_parquet(INPUT_PATH),
        assumptions,
        risk_free_column=f"indicator_{cost.risk_free_indicator}",
    )


def main() -> None:
    frame = run_benchmark_valuation()
    path = write_parquet_atomic(frame, OUTPUT_PATH)
    print(f"row_count={frame.height}")
    print(
        frame.group_by(["ticker", "model_name"])
        .agg(
            pl.len().alias("rows"),
            pl.col("valuation_date").min().alias("min_valuation_date"),
            pl.col("valuation_date").max().alias("max_valuation_date"),
            pl.col("model_value").null_count().alias("null_values"),
        )
        .sort(["ticker", "model_name"])
    )
    print(f"schema={frame.schema}")
    print(f"output_path={path}")


if __name__ == "__main__":
    main()
