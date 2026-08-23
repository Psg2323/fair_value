from datetime import date

import polars as pl
import pytest

from fair_value.valuation.benchmarks import (
    BenchmarkAssumptions,
    book_value_benchmark,
    build_benchmark_valuations,
    estimate_cost_of_equity,
    no_growth_residual_income_value,
)


def test_pure_benchmark_formulas() -> None:
    assert book_value_benchmark(100.0) == 100.0
    assert estimate_cost_of_equity(
        0.03,
        equity_risk_premium=0.05,
        beta=1.0,
        minimum=0.06,
        maximum=0.20,
    ) == pytest.approx(0.08)
    assert no_growth_residual_income_value(100.0, 12.0, 0.10) == pytest.approx(120.0)


def test_build_benchmark_valuations_uses_asof_inputs() -> None:
    asof_data = pl.DataFrame(
        {
            "valuation_date": [date(2025, 5, 30)],
            "ticker": ["005930"],
            "market_price": [60_000.0],
            "equity_per_price_basis_share": [50_000.0],
            "earnings_per_price_basis_share_ttm": [8_000.0],
            "indicator_korea_treasury_3y": [3.0],
            "financial_period_end": [date(2025, 3, 31)],
            "financial_available_at": [date(2025, 5, 15)],
        }
    )
    assumptions = BenchmarkAssumptions(
        version="test_v1",
        risk_free_rate_scale=0.01,
        equity_risk_premium=0.05,
        beta=1.0,
        minimum_cost_of_equity=0.06,
        maximum_cost_of_equity=0.20,
    )

    result = build_benchmark_valuations(
        asof_data,
        assumptions,
        risk_free_column="indicator_korea_treasury_3y",
    )

    assert result.height == 2
    book = result.filter(pl.col("model_name") == "book_value").row(0, named=True)
    rim = result.filter(pl.col("model_name") == "no_growth_rim").row(0, named=True)
    assert book["model_value"] == pytest.approx(50_000.0)
    assert rim["cost_of_equity"] == pytest.approx(0.08)
    assert rim["model_value"] == pytest.approx(100_000.0)
    assert result.get_column("assumptions_version").unique().to_list() == ["test_v1"]


def test_benchmark_rejects_missing_columns() -> None:
    assumptions = BenchmarkAssumptions(
        version="test_v1",
        risk_free_rate_scale=0.01,
        equity_risk_premium=0.05,
        beta=1.0,
        minimum_cost_of_equity=0.06,
        maximum_cost_of_equity=0.20,
    )

    with pytest.raises(ValueError, match="Missing benchmark input columns"):
        build_benchmark_valuations(
            pl.DataFrame({"ticker": ["005930"]}),
            assumptions,
            risk_free_column="indicator_korea_treasury_3y",
        )
