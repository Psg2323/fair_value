from __future__ import annotations

import polars as pl

from fair_value.config_loader import ValuationConfig, load_valuation
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic
from fair_value.valuation.cycle_rim import (
    RANGE_SCENARIOS,
    CycleRimAssumptions,
    CycleRimScenario,
    build_cycle_rim_scenarios,
    build_fair_value_range,
)

INPUT_PATH = PROJECT_ROOT / "data" / "gold" / "model_inputs" / "valuation_asof_monthly.parquet"
SCENARIO_OUTPUT_PATH = PROJECT_ROOT / "data" / "gold" / "valuation" / "cycle_rim_scenarios.parquet"
RANGE_OUTPUT_PATH = PROJECT_ROOT / "data" / "gold" / "valuation" / "fair_value_range.parquet"


def build_model_parameters(
    config: ValuationConfig,
) -> tuple[CycleRimAssumptions, tuple[CycleRimScenario, ...]]:
    cost = config.cost_of_equity
    rim = config.cycle_normalized_rim
    assumptions = CycleRimAssumptions(
        version=rim.version,
        forecast_years=rim.forecast_years,
        retention_ratio=rim.retention_ratio,
        minimum_normalized_roe=rim.minimum_normalized_roe,
        maximum_normalized_roe=rim.maximum_normalized_roe,
        maximum_cycle_roe_adjustment=rim.maximum_cycle_roe_adjustment,
        risk_free_rate_scale=cost.risk_free_rate_scale,
        equity_risk_premium=cost.equity_risk_premium,
        beta=cost.beta,
        minimum_cost_of_equity=cost.minimum,
        maximum_cost_of_equity=cost.maximum,
        industrial_production_scale=rim.industrial_production_scale,
        producer_price_scale=rim.producer_price_scale,
    )
    scenarios = tuple(
        CycleRimScenario(
            name=name,
            normalized_roe_delta=rim.scenarios[name].normalized_roe_delta,
            equity_risk_premium_delta=rim.scenarios[name].equity_risk_premium_delta,
        )
        for name in RANGE_SCENARIOS
    )
    return assumptions, scenarios


def run_cycle_rim_valuation() -> tuple[pl.DataFrame, pl.DataFrame]:
    config = load_valuation()
    assumptions, scenarios = build_model_parameters(config)
    rim = config.cycle_normalized_rim
    scenario_values = build_cycle_rim_scenarios(
        pl.read_parquet(INPUT_PATH),
        assumptions,
        scenarios,
        risk_free_column=f"indicator_{config.cost_of_equity.risk_free_indicator}",
        industrial_production_column=rim.industrial_production_column,
        producer_price_column=rim.producer_price_column,
    )
    return scenario_values, build_fair_value_range(scenario_values)


def main() -> None:
    scenarios, ranges = run_cycle_rim_valuation()
    scenario_path = write_parquet_atomic(scenarios, SCENARIO_OUTPUT_PATH)
    range_path = write_parquet_atomic(ranges, RANGE_OUTPUT_PATH)
    print(f"scenario_row_count={scenarios.height}")
    print(f"range_row_count={ranges.height}")
    print(
        ranges.group_by("ticker")
        .agg(
            pl.len().alias("rows"),
            pl.col("valuation_date").min().alias("min_valuation_date"),
            pl.col("valuation_date").max().alias("max_valuation_date"),
            pl.col("fair_value_low").null_count().alias("null_ranges"),
        )
        .sort("ticker")
    )
    print(f"range_schema={ranges.schema}")
    print(f"scenario_output_path={scenario_path}")
    print(f"range_output_path={range_path}")


if __name__ == "__main__":
    main()
