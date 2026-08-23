from datetime import date

import polars as pl

from fair_value.valuation.cycle_rim import (
    CycleRimAssumptions,
    CycleRimScenario,
)
from fair_value.valuation.sensitivity import (
    SensitivityVariant,
    build_cycle_rim_sensitivity_ranges,
)


def _assumptions(version: str, forecast_years: int) -> CycleRimAssumptions:
    return CycleRimAssumptions(
        version=version,
        forecast_years=forecast_years,
        retention_ratio=0.5,
        minimum_normalized_roe=0.0,
        maximum_normalized_roe=0.3,
        maximum_cycle_roe_adjustment=0.02,
        risk_free_rate_scale=0.01,
        equity_risk_premium=0.05,
        beta=1.0,
        minimum_cost_of_equity=0.06,
        maximum_cost_of_equity=0.20,
        industrial_production_scale=0.10,
        producer_price_scale=0.10,
    )


def test_sensitivity_keeps_variants_separate_and_auditable() -> None:
    asof = pl.DataFrame(
        {
            "valuation_date": [date(2025, 5, 30)],
            "ticker": ["005930"],
            "market_price": [50_000.0],
            "equity_per_price_basis_share": [60_000.0],
            "roe_ttm_5y_median_candidate": [0.15],
            "risk_free": [3.0],
            "production": [0.10],
            "producer_price": [0.05],
            "financial_period_end": [date(2025, 3, 31)],
            "financial_available_at": [date(2025, 5, 15)],
        }
    )
    variants = (
        SensitivityVariant("base", _assumptions("base", 5)),
        SensitivityVariant("short_fade", _assumptions("short", 3)),
    )
    scenarios = (
        CycleRimScenario("low", -0.02, 0.015),
        CycleRimScenario("base", 0.0, 0.0),
        CycleRimScenario("high", 0.02, -0.015),
    )

    result = build_cycle_rim_sensitivity_ranges(
        asof,
        variants,
        scenarios,
        risk_free_column="risk_free",
        industrial_production_column="production",
        producer_price_column="producer_price",
    )

    assert result.height == 2
    assert result["model_variant"].to_list() == ["base", "short_fade"]
    assert result["forecast_years"].to_list() == [5, 3]
