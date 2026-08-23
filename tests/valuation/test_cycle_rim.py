from datetime import date

import polars as pl
import pytest

from fair_value.valuation.cycle_rim import (
    CycleRimAssumptions,
    CycleRimScenario,
    bounded_cycle_score,
    build_cycle_rim_scenarios,
    build_fair_value_range,
    cycle_normalized_roe,
    finite_fade_residual_income_value,
)


def _assumptions() -> CycleRimAssumptions:
    return CycleRimAssumptions(
        version="test_v0",
        forecast_years=5,
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


def _scenarios() -> tuple[CycleRimScenario, ...]:
    return (
        CycleRimScenario("low", -0.02, 0.015),
        CycleRimScenario("base", 0.0, 0.0),
        CycleRimScenario("high", 0.02, -0.015),
    )


def test_cycle_normalization_is_bounded_and_countercyclical() -> None:
    assert bounded_cycle_score(
        0.20,
        0.05,
        industrial_production_scale=0.10,
        producer_price_scale=0.10,
    ) == pytest.approx(0.75)
    assert cycle_normalized_roe(
        0.15,
        1.0,
        maximum_cycle_adjustment=0.02,
        minimum=0.0,
        maximum=0.30,
    ) == pytest.approx(0.13)


def test_finite_fade_rim_equals_book_when_roe_equals_cost() -> None:
    assert finite_fade_residual_income_value(
        100.0,
        0.08,
        0.08,
        retention_ratio=0.5,
        forecast_years=5,
    ) == pytest.approx(100.0)
    assert (
        finite_fade_residual_income_value(
            100.0,
            0.15,
            0.08,
            retention_ratio=0.5,
            forecast_years=5,
        )
        > 100.0
    )


def test_scenarios_create_monotonic_range_without_using_market_as_input() -> None:
    frame = pl.DataFrame(
        {
            "valuation_date": [date(2025, 5, 30), date(2025, 6, 30)],
            "ticker": ["005930", "005930"],
            "market_price": [50_000.0, 100_000.0],
            "equity_per_price_basis_share": [60_000.0, 60_000.0],
            "roe_ttm_5y_median_candidate": [0.15, 0.15],
            "indicator_korea_treasury_3y": [3.0, 3.0],
            "global_cycle_us_semiconductor_industrial_production_yoy": [0.10, 0.10],
            "global_cycle_us_semiconductor_producer_price_index_yoy": [0.05, 0.05],
            "financial_period_end": [date(2025, 3, 31), date(2025, 3, 31)],
            "financial_available_at": [date(2025, 5, 15), date(2025, 5, 15)],
        }
    )

    scenarios = build_cycle_rim_scenarios(
        frame,
        _assumptions(),
        _scenarios(),
        risk_free_column="indicator_korea_treasury_3y",
        industrial_production_column=("global_cycle_us_semiconductor_industrial_production_yoy"),
        producer_price_column=("global_cycle_us_semiconductor_producer_price_index_yoy"),
    )
    ranges = build_fair_value_range(scenarios)

    assert scenarios.height == 6
    assert ranges.height == 2
    first = ranges.row(0, named=True)
    assert first["fair_value_low"] <= first["fair_value_base"] <= first["fair_value_high"]
    base_values = scenarios.filter(pl.col("scenario") == "base").get_column("model_value")
    assert base_values[0] == pytest.approx(base_values[1])
