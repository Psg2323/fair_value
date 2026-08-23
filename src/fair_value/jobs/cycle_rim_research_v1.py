from __future__ import annotations

from dataclasses import replace
from math import isclose

import polars as pl

from fair_value.backtest.engine import add_range_coverage, evaluate_future_returns
from fair_value.backtest.report import (
    build_backtest_summary,
    select_non_overlapping_horizons,
)
from fair_value.backtest.walk_forward import (
    assign_fixed_assumption_walk_forward_folds,
)
from fair_value.config_loader import (
    CycleRimSensitivityConfig,
    load_valuation,
    load_valuation_sensitivity,
)
from fair_value.jobs.cycle_rim_valuation import build_model_parameters
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic
from fair_value.valuation.cycle_rim import CYCLE_RIM_MODEL, CycleRimAssumptions
from fair_value.valuation.sensitivity import (
    SensitivityVariant,
    build_cycle_rim_sensitivity_ranges,
)

ASOF_PATH = PROJECT_ROOT / "data" / "gold" / "model_inputs" / "valuation_asof_monthly.parquet"
MARKET_PATH = PROJECT_ROOT / "data" / "silver" / "market_price" / "canonical.parquet"
RESEARCH_ROOT = PROJECT_ROOT / "data" / "gold" / "research" / "cycle_rim_v1"
RANGE_PATH = RESEARCH_ROOT / "sensitivity_ranges.parquet"
FUTURE_RETURN_PATH = RESEARCH_ROOT / "sensitivity_future_returns.parquet"
NON_OVERLAPPING_PATH = RESEARCH_ROOT / "sensitivity_non_overlapping.parquet"
SENSITIVITY_SUMMARY_PATH = RESEARCH_ROOT / "sensitivity_summary.parquet"
WALK_FORWARD_PATH = RESEARCH_ROOT / "walk_forward_results.parquet"
WALK_FORWARD_SUMMARY_PATH = RESEARCH_ROOT / "walk_forward_summary.parquet"


def build_sensitivity_variants(
    base: CycleRimAssumptions,
    config: CycleRimSensitivityConfig,
) -> tuple[SensitivityVariant, ...]:
    variants = [SensitivityVariant("base", replace(base, version=f"{config.version}:base"))]

    for years in config.forecast_years:
        if years == base.forecast_years:
            continue
        name = f"forecast_years_{years}"
        variants.append(
            SensitivityVariant(
                name,
                replace(base, version=f"{config.version}:{name}", forecast_years=years),
            )
        )
    for ratio in config.retention_ratios:
        if isclose(ratio, base.retention_ratio):
            continue
        name = f"retention_ratio_{_float_token(ratio)}"
        variants.append(
            SensitivityVariant(
                name,
                replace(base, version=f"{config.version}:{name}", retention_ratio=ratio),
            )
        )
    for adjustment in config.maximum_cycle_roe_adjustments:
        if isclose(adjustment, base.maximum_cycle_roe_adjustment):
            continue
        name = f"cycle_adjustment_{_float_token(adjustment)}"
        variants.append(
            SensitivityVariant(
                name,
                replace(
                    base,
                    version=f"{config.version}:{name}",
                    maximum_cycle_roe_adjustment=adjustment,
                ),
            )
        )
    for delta in config.equity_risk_premium_deltas:
        if isclose(delta, 0.0):
            continue
        direction = "minus" if delta < 0 else "plus"
        name = f"erp_{direction}_{_float_token(abs(delta))}"
        variants.append(
            SensitivityVariant(
                name,
                replace(
                    base,
                    version=f"{config.version}:{name}",
                    equity_risk_premium=base.equity_risk_premium + delta,
                ),
            )
        )
    return tuple(variants)


def run_cycle_rim_research_v1() -> dict[str, pl.DataFrame]:
    valuation_config = load_valuation()
    sensitivity_config = load_valuation_sensitivity()
    base, scenarios = build_model_parameters(valuation_config)
    rim = valuation_config.cycle_normalized_rim
    ranges = build_cycle_rim_sensitivity_ranges(
        pl.read_parquet(ASOF_PATH),
        build_sensitivity_variants(base, sensitivity_config),
        scenarios,
        risk_free_column=(f"indicator_{valuation_config.cost_of_equity.risk_free_indicator}"),
        industrial_production_column=rim.industrial_production_column,
        producer_price_column=rim.producer_price_column,
    )
    valuation_rows = ranges.with_columns(
        pl.lit(CYCLE_RIM_MODEL).alias("model_name"),
        pl.col("fair_value_base").alias("model_value"),
        pl.col("base_value_to_price").alias("value_to_price"),
    )
    evaluated = add_range_coverage(
        evaluate_future_returns(
            valuation_rows,
            pl.read_parquet(MARKET_PATH),
        )
    )
    series_columns = ("model_variant", "ticker", "horizon_months")
    non_overlapping = select_non_overlapping_horizons(
        evaluated,
        series_columns=series_columns,
    )
    sensitivity_summary = build_backtest_summary(
        non_overlapping,
        group_columns=series_columns,
    )
    walk_forward = assign_fixed_assumption_walk_forward_folds(
        non_overlapping,
        initial_training_years=sensitivity_config.initial_training_years,
    )
    walk_forward_summary = build_backtest_summary(
        walk_forward,
        group_columns=(
            "model_variant",
            "ticker",
            "test_year",
            "horizon_months",
        ),
    )
    return {
        "ranges": ranges,
        "future_returns": evaluated,
        "non_overlapping": non_overlapping,
        "sensitivity_summary": sensitivity_summary,
        "walk_forward": walk_forward,
        "walk_forward_summary": walk_forward_summary,
    }


def _float_token(value: float) -> str:
    return f"{value:.3f}".replace(".", "p")


def main() -> None:
    frames = run_cycle_rim_research_v1()
    output_paths = {
        "ranges": RANGE_PATH,
        "future_returns": FUTURE_RETURN_PATH,
        "non_overlapping": NON_OVERLAPPING_PATH,
        "sensitivity_summary": SENSITIVITY_SUMMARY_PATH,
        "walk_forward": WALK_FORWARD_PATH,
        "walk_forward_summary": WALK_FORWARD_SUMMARY_PATH,
    }
    for name, frame in frames.items():
        path = write_parquet_atomic(frame, output_paths[name])
        print(f"research_output={name} rows={frame.height} output_path={path}")

    latest = (
        frames["ranges"]
        .sort(["model_variant", "ticker", "valuation_date"])
        .group_by(["model_variant", "ticker"], maintain_order=True)
        .last()
        .select(
            "model_variant",
            "ticker",
            "valuation_date",
            "fair_value_base",
            "base_value_to_price",
        )
    )
    print(latest)


if __name__ == "__main__":
    main()
