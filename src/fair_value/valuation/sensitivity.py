from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

from fair_value.valuation.cycle_rim import (
    CycleRimAssumptions,
    CycleRimScenario,
    build_cycle_rim_scenarios,
    build_fair_value_range,
)


@dataclass(frozen=True, slots=True)
class SensitivityVariant:
    """One named, predeclared set of research assumptions."""

    name: str
    assumptions: CycleRimAssumptions

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Sensitivity variant name must not be empty")


def build_cycle_rim_sensitivity_ranges(
    asof_data: pl.DataFrame,
    variants: Sequence[SensitivityVariant],
    scenarios: tuple[CycleRimScenario, ...],
    *,
    risk_free_column: str,
    industrial_production_column: str,
    producer_price_column: str,
) -> pl.DataFrame:
    """Apply one-at-a-time variants without selecting a winner from future returns."""
    if not variants:
        raise ValueError("At least one sensitivity variant is required")
    names = [variant.name for variant in variants]
    if len(set(names)) != len(names):
        raise ValueError("Sensitivity variant names must be unique")

    outputs: list[pl.DataFrame] = []
    for variant in variants:
        scenario_values = build_cycle_rim_scenarios(
            asof_data,
            variant.assumptions,
            scenarios,
            risk_free_column=risk_free_column,
            industrial_production_column=industrial_production_column,
            producer_price_column=producer_price_column,
        )
        outputs.append(
            build_fair_value_range(scenario_values).with_columns(
                pl.lit(variant.name).alias("model_variant"),
                pl.lit(variant.assumptions.forecast_years).cast(pl.Int16).alias("forecast_years"),
                pl.lit(variant.assumptions.retention_ratio).alias("retention_ratio"),
                pl.lit(variant.assumptions.maximum_cycle_roe_adjustment).alias(
                    "maximum_cycle_roe_adjustment"
                ),
                pl.lit(variant.assumptions.equity_risk_premium).alias("equity_risk_premium"),
            )
        )

    return pl.concat(outputs, how="vertical").sort(["model_variant", "ticker", "valuation_date"])
