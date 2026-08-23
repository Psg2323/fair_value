from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import polars as pl

BOOK_VALUE_MODEL = "book_value"
NO_GROWTH_RIM_MODEL = "no_growth_rim"


@dataclass(frozen=True)
class BenchmarkAssumptions:
    """Versioned research assumptions for benchmark valuation."""

    version: str
    risk_free_rate_scale: float
    equity_risk_premium: float
    beta: float
    minimum_cost_of_equity: float
    maximum_cost_of_equity: float

    def __post_init__(self) -> None:
        numeric_values = (
            self.risk_free_rate_scale,
            self.equity_risk_premium,
            self.beta,
            self.minimum_cost_of_equity,
            self.maximum_cost_of_equity,
        )
        if not all(isfinite(value) for value in numeric_values):
            raise ValueError("Benchmark assumptions must be finite")
        if self.risk_free_rate_scale <= 0:
            raise ValueError("risk_free_rate_scale must be positive")
        if self.minimum_cost_of_equity <= 0:
            raise ValueError("minimum_cost_of_equity must be positive")
        if self.maximum_cost_of_equity < self.minimum_cost_of_equity:
            raise ValueError("maximum_cost_of_equity must not be below minimum")


def estimate_cost_of_equity(
    risk_free_rate: float,
    *,
    equity_risk_premium: float,
    beta: float,
    minimum: float,
    maximum: float,
) -> float:
    """Estimate CAPM-style cost of equity and bound unstable inputs."""
    values = (risk_free_rate, equity_risk_premium, beta, minimum, maximum)
    if not all(isfinite(value) for value in values):
        raise ValueError("Cost-of-equity inputs must be finite")
    if minimum <= 0 or maximum < minimum:
        raise ValueError("Invalid cost-of-equity bounds")
    return min(max(risk_free_rate + beta * equity_risk_premium, minimum), maximum)


def book_value_benchmark(book_value_per_share: float) -> float:
    """Use point-in-time parent equity per distributed share as value."""
    if not isfinite(book_value_per_share):
        raise ValueError("book_value_per_share must be finite")
    return book_value_per_share


def no_growth_residual_income_value(
    book_value_per_share: float,
    earnings_per_share: float,
    cost_of_equity: float,
) -> float:
    """Value current residual income as a zero-growth perpetuity."""
    values = (book_value_per_share, earnings_per_share, cost_of_equity)
    if not all(isfinite(value) for value in values):
        raise ValueError("No-growth RIM inputs must be finite")
    if cost_of_equity <= 0:
        raise ValueError("cost_of_equity must be positive")
    residual_income = earnings_per_share - cost_of_equity * book_value_per_share
    return book_value_per_share + residual_income / cost_of_equity


def build_benchmark_valuations(
    asof_data: pl.DataFrame,
    assumptions: BenchmarkAssumptions,
    *,
    risk_free_column: str,
) -> pl.DataFrame:
    """Apply pure benchmark formulas to point-in-time model inputs."""
    required = {
        "valuation_date",
        "ticker",
        "market_price",
        "equity_per_price_basis_share",
        "earnings_per_price_basis_share_ttm",
        "financial_period_end",
        "financial_available_at",
        risk_free_column,
    }
    missing = required - set(asof_data.columns)
    if missing:
        raise ValueError(f"Missing benchmark input columns: {sorted(missing)}")

    input_frame = asof_data.select(
        "valuation_date",
        "ticker",
        pl.col("market_price").cast(pl.Float64),
        pl.col("equity_per_price_basis_share").cast(pl.Float64).alias("book_value_per_share"),
        pl.col("earnings_per_price_basis_share_ttm")
        .cast(pl.Float64)
        .alias("earnings_per_share_ttm"),
        pl.col(risk_free_column).cast(pl.Float64).alias("_risk_free_raw"),
        "financial_period_end",
        "financial_available_at",
    )

    book_value = input_frame.filter(
        pl.col("market_price").is_not_null()
        & (pl.col("market_price") > 0)
        & pl.col("book_value_per_share").is_not_null()
    ).with_columns(
        pl.lit(BOOK_VALUE_MODEL).alias("model_name"),
        pl.col("book_value_per_share").alias("model_value"),
        pl.lit(None, dtype=pl.Float64).alias("residual_income_per_share"),
        pl.lit(None, dtype=pl.Float64).alias("risk_free_rate"),
        pl.lit(None, dtype=pl.Float64).alias("cost_of_equity"),
    )

    no_growth = (
        input_frame.filter(
            pl.col("market_price").is_not_null()
            & (pl.col("market_price") > 0)
            & pl.col("book_value_per_share").is_not_null()
            & pl.col("earnings_per_share_ttm").is_not_null()
            & pl.col("_risk_free_raw").is_not_null()
        )
        .with_columns(
            (pl.col("_risk_free_raw") * assumptions.risk_free_rate_scale).alias("risk_free_rate")
        )
        .with_columns(
            (pl.col("risk_free_rate") + assumptions.beta * assumptions.equity_risk_premium)
            .clip(
                assumptions.minimum_cost_of_equity,
                assumptions.maximum_cost_of_equity,
            )
            .alias("cost_of_equity")
        )
        .with_columns(
            (
                pl.col("earnings_per_share_ttm")
                - pl.col("cost_of_equity") * pl.col("book_value_per_share")
            ).alias("residual_income_per_share")
        )
        .with_columns(
            pl.lit(NO_GROWTH_RIM_MODEL).alias("model_name"),
            (
                pl.col("book_value_per_share")
                + pl.col("residual_income_per_share") / pl.col("cost_of_equity")
            ).alias("model_value"),
        )
    )

    output_columns = [
        "valuation_date",
        "ticker",
        "model_name",
        "market_price",
        "model_value",
        "book_value_per_share",
        "earnings_per_share_ttm",
        "residual_income_per_share",
        "risk_free_rate",
        "cost_of_equity",
        "financial_period_end",
        "financial_available_at",
    ]
    return (
        pl.concat(
            [book_value.select(output_columns), no_growth.select(output_columns)],
            how="vertical",
        )
        .with_columns(
            (pl.col("model_value") / pl.col("market_price")).alias("value_to_price"),
            pl.lit(assumptions.version).alias("assumptions_version"),
        )
        .sort(["ticker", "valuation_date", "model_name"])
    )
