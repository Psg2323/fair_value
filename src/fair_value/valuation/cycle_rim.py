from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

import polars as pl

CYCLE_RIM_MODEL = "cycle_normalized_rim"
ScenarioName = Literal["low", "base", "high"]
RANGE_SCENARIOS: tuple[ScenarioName, ...] = ("low", "base", "high")


@dataclass(frozen=True)
class CycleRimScenario:
    """One explicit normalized-ROE and risk-premium sensitivity."""

    name: str
    normalized_roe_delta: float
    equity_risk_premium_delta: float

    def __post_init__(self) -> None:
        if self.name not in RANGE_SCENARIOS:
            raise ValueError(f"Unsupported scenario: {self.name}")
        if not isfinite(self.normalized_roe_delta):
            raise ValueError("normalized_roe_delta must be finite")
        if not isfinite(self.equity_risk_premium_delta):
            raise ValueError("equity_risk_premium_delta must be finite")


@dataclass(frozen=True)
class CycleRimAssumptions:
    """Versioned research assumptions for finite-fade residual income."""

    version: str
    forecast_years: int
    retention_ratio: float
    minimum_normalized_roe: float
    maximum_normalized_roe: float
    maximum_cycle_roe_adjustment: float
    risk_free_rate_scale: float
    equity_risk_premium: float
    beta: float
    minimum_cost_of_equity: float
    maximum_cost_of_equity: float
    industrial_production_scale: float
    producer_price_scale: float

    def __post_init__(self) -> None:
        if self.forecast_years <= 0:
            raise ValueError("forecast_years must be positive")
        if not 0 <= self.retention_ratio <= 1:
            raise ValueError("retention_ratio must be between zero and one")
        if self.maximum_normalized_roe < self.minimum_normalized_roe:
            raise ValueError("Invalid normalized-ROE bounds")
        if self.maximum_cycle_roe_adjustment < 0:
            raise ValueError("maximum_cycle_roe_adjustment must not be negative")
        if self.risk_free_rate_scale <= 0:
            raise ValueError("risk_free_rate_scale must be positive")
        if self.minimum_cost_of_equity <= 0:
            raise ValueError("minimum_cost_of_equity must be positive")
        if self.maximum_cost_of_equity < self.minimum_cost_of_equity:
            raise ValueError("Invalid cost-of-equity bounds")
        if self.industrial_production_scale <= 0 or self.producer_price_scale <= 0:
            raise ValueError("Cycle signal scales must be positive")


def bounded_cycle_score(
    industrial_production_yoy: float,
    producer_price_yoy: float,
    *,
    industrial_production_scale: float,
    producer_price_scale: float,
) -> float:
    """Combine two cycle observations into a bounded normalization aid."""
    values = (
        industrial_production_yoy,
        producer_price_yoy,
        industrial_production_scale,
        producer_price_scale,
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("Cycle-score inputs must be finite")
    if industrial_production_scale <= 0 or producer_price_scale <= 0:
        raise ValueError("Cycle signal scales must be positive")
    production_signal = max(
        -1.0,
        min(industrial_production_yoy / industrial_production_scale, 1.0),
    )
    price_signal = max(
        -1.0,
        min(producer_price_yoy / producer_price_scale, 1.0),
    )
    return (production_signal + price_signal) / 2.0


def cycle_normalized_roe(
    long_run_roe: float,
    cycle_score: float,
    *,
    maximum_cycle_adjustment: float,
    minimum: float,
    maximum: float,
) -> float:
    """Make the long-run ROE assumption modestly countercyclical."""
    values = (long_run_roe, cycle_score, maximum_cycle_adjustment, minimum, maximum)
    if not all(isfinite(value) for value in values):
        raise ValueError("Normalized-ROE inputs must be finite")
    if not -1 <= cycle_score <= 1:
        raise ValueError("cycle_score must be between -1 and 1")
    if maximum_cycle_adjustment < 0 or maximum < minimum:
        raise ValueError("Invalid normalized-ROE bounds")
    adjusted = long_run_roe - cycle_score * maximum_cycle_adjustment
    return min(max(adjusted, minimum), maximum)


def finite_fade_residual_income_value(
    book_value_per_share: float,
    normalized_roe: float,
    cost_of_equity: float,
    *,
    retention_ratio: float,
    forecast_years: int,
) -> float:
    """Discount residual income while excess ROE fades linearly to zero."""
    values = (book_value_per_share, normalized_roe, cost_of_equity, retention_ratio)
    if not all(isfinite(value) for value in values):
        raise ValueError("RIM inputs must be finite")
    if book_value_per_share < 0:
        raise ValueError("book_value_per_share must not be negative")
    if cost_of_equity <= 0:
        raise ValueError("cost_of_equity must be positive")
    if not 0 <= retention_ratio <= 1:
        raise ValueError("retention_ratio must be between zero and one")
    if forecast_years <= 0:
        raise ValueError("forecast_years must be positive")

    opening_book = book_value_per_share
    value = book_value_per_share
    excess_roe = normalized_roe - cost_of_equity
    for year in range(1, forecast_years + 1):
        fade_weight = (forecast_years - year + 1) / forecast_years
        forecast_roe = cost_of_equity + excess_roe * fade_weight
        residual_income = (forecast_roe - cost_of_equity) * opening_book
        value += residual_income / (1.0 + cost_of_equity) ** year
        opening_book += forecast_roe * opening_book * retention_ratio
    return max(value, 0.0)


def build_cycle_rim_scenarios(
    asof_data: pl.DataFrame,
    assumptions: CycleRimAssumptions,
    scenarios: tuple[CycleRimScenario, ...],
    *,
    risk_free_column: str,
    industrial_production_column: str,
    producer_price_column: str,
) -> pl.DataFrame:
    """Apply the research RIM using only point-in-time input columns."""
    if {scenario.name for scenario in scenarios} != set(RANGE_SCENARIOS):
        raise ValueError("Exactly low, base, and high scenarios are required")
    required = {
        "valuation_date",
        "ticker",
        "market_price",
        "equity_per_price_basis_share",
        "roe_ttm_5y_median_candidate",
        "financial_period_end",
        "financial_available_at",
        risk_free_column,
        industrial_production_column,
        producer_price_column,
    }
    missing = required - set(asof_data.columns)
    if missing:
        raise ValueError(f"Missing cycle RIM input columns: {sorted(missing)}")

    frame = (
        asof_data.select(
            "valuation_date",
            "ticker",
            pl.col("market_price").cast(pl.Float64),
            pl.col("equity_per_price_basis_share").cast(pl.Float64).alias("book_value_per_share"),
            pl.col("roe_ttm_5y_median_candidate").cast(pl.Float64).alias("long_run_roe"),
            pl.col(risk_free_column).cast(pl.Float64).alias("_risk_free_raw"),
            pl.col(industrial_production_column).cast(pl.Float64).alias("_production_yoy"),
            pl.col(producer_price_column).cast(pl.Float64).alias("_producer_price_yoy"),
            "financial_period_end",
            "financial_available_at",
        )
        .filter(
            pl.col("market_price").is_not_null()
            & (pl.col("market_price") > 0)
            & pl.col("book_value_per_share").is_not_null()
            & (pl.col("book_value_per_share") >= 0)
            & pl.col("long_run_roe").is_not_null()
            & pl.col("_risk_free_raw").is_not_null()
            & pl.col("_production_yoy").is_not_null()
            & pl.col("_producer_price_yoy").is_not_null()
        )
        .with_columns(
            (
                (pl.col("_production_yoy") / assumptions.industrial_production_scale).clip(
                    -1.0, 1.0
                )
                + (pl.col("_producer_price_yoy") / assumptions.producer_price_scale).clip(-1.0, 1.0)
            )
            .truediv(2.0)
            .alias("cycle_score"),
            (pl.col("_risk_free_raw") * assumptions.risk_free_rate_scale).alias("risk_free_rate"),
        )
        .with_columns(
            (
                pl.col("long_run_roe")
                - pl.col("cycle_score") * assumptions.maximum_cycle_roe_adjustment
            )
            .clip(
                assumptions.minimum_normalized_roe,
                assumptions.maximum_normalized_roe,
            )
            .alias("_cycle_normalized_roe")
        )
    )

    outputs: list[pl.DataFrame] = []
    for scenario in scenarios:
        scenario_frame = (
            frame.with_columns(
                (
                    pl.col("risk_free_rate")
                    + assumptions.beta
                    * (assumptions.equity_risk_premium + scenario.equity_risk_premium_delta)
                )
                .clip(
                    assumptions.minimum_cost_of_equity,
                    assumptions.maximum_cost_of_equity,
                )
                .alias("cost_of_equity"),
                (pl.col("_cycle_normalized_roe") + scenario.normalized_roe_delta)
                .clip(
                    assumptions.minimum_normalized_roe,
                    assumptions.maximum_normalized_roe,
                )
                .alias("normalized_roe"),
            )
            .with_columns(
                _finite_fade_value_expression(assumptions).alias("model_value"),
                pl.lit(CYCLE_RIM_MODEL).alias("model_name"),
                pl.lit(scenario.name).alias("scenario"),
                pl.lit(assumptions.version).alias("model_version"),
            )
            .with_columns((pl.col("model_value") / pl.col("market_price")).alias("value_to_price"))
        )
        outputs.append(scenario_frame)

    output_columns = [
        "valuation_date",
        "ticker",
        "model_name",
        "scenario",
        "market_price",
        "model_value",
        "value_to_price",
        "book_value_per_share",
        "long_run_roe",
        "cycle_score",
        "normalized_roe",
        "risk_free_rate",
        "cost_of_equity",
        "financial_period_end",
        "financial_available_at",
        "model_version",
    ]
    return pl.concat(
        [output.select(output_columns) for output in outputs],
        how="vertical",
    ).sort(["ticker", "valuation_date", "scenario"])


def build_fair_value_range(scenarios: pl.DataFrame) -> pl.DataFrame:
    """Pivot explicit scenarios into the MVP fair-value range contract."""
    required = {
        "valuation_date",
        "ticker",
        "scenario",
        "model_value",
        "market_price",
        "cycle_score",
        "normalized_roe",
        "cost_of_equity",
        "financial_period_end",
        "financial_available_at",
        "model_version",
    }
    missing = required - set(scenarios.columns)
    if missing:
        raise ValueError(f"Missing range columns: {sorted(missing)}")
    present = set(scenarios.get_column("scenario").unique().to_list())
    if present != set(RANGE_SCENARIOS):
        raise ValueError("Exactly low, base, and high scenarios are required")
    duplicates = (
        scenarios.group_by(["ticker", "valuation_date", "scenario"])
        .len()
        .filter(pl.col("len") != 1)
    )
    if duplicates.height:
        raise ValueError("Scenario rows must be unique by ticker and valuation_date")

    values = (
        scenarios.select("valuation_date", "ticker", "scenario", "model_value")
        .pivot(
            on="scenario",
            index=["valuation_date", "ticker"],
            values="model_value",
            aggregate_function=None,
        )
        .rename(
            {
                "low": "fair_value_low",
                "base": "fair_value_base",
                "high": "fair_value_high",
            }
        )
    )
    base_inputs = scenarios.filter(pl.col("scenario") == "base").select(
        "valuation_date",
        "ticker",
        "market_price",
        "cycle_score",
        pl.col("normalized_roe").alias("normalized_roe_base"),
        pl.col("cost_of_equity").alias("cost_of_equity_base"),
        "financial_period_end",
        "financial_available_at",
        "model_version",
    )
    result = values.join(
        base_inputs,
        on=["valuation_date", "ticker"],
        how="inner",
        validate="1:1",
    ).sort(["ticker", "valuation_date"])
    invalid = result.filter(
        (pl.col("fair_value_low") > pl.col("fair_value_base"))
        | (pl.col("fair_value_base") > pl.col("fair_value_high"))
    )
    if invalid.height:
        raise ValueError(f"Non-monotonic fair-value range in {invalid.height} rows")
    return (
        result.with_columns(
            (pl.col("fair_value_base") / pl.col("market_price")).alias("base_value_to_price")
        )
        .select(
            "valuation_date",
            "ticker",
            "fair_value_low",
            "fair_value_base",
            "fair_value_high",
            "market_price",
            "base_value_to_price",
            "cycle_score",
            "normalized_roe_base",
            "cost_of_equity_base",
            "financial_period_end",
            "financial_available_at",
            "model_version",
        )
        .sort(["ticker", "valuation_date"])
    )


def _finite_fade_value_expression(assumptions: CycleRimAssumptions) -> pl.Expr:
    opening_book = pl.col("book_value_per_share")
    cost_of_equity = pl.col("cost_of_equity")
    excess_roe = pl.col("normalized_roe") - cost_of_equity
    value = opening_book
    for year in range(1, assumptions.forecast_years + 1):
        fade_weight = (assumptions.forecast_years - year + 1) / assumptions.forecast_years
        forecast_roe = cost_of_equity + excess_roe * fade_weight
        residual_income = (forecast_roe - cost_of_equity) * opening_book
        value = value + residual_income / (1.0 + cost_of_equity).pow(year)
        opening_book = opening_book + forecast_roe * opening_book * assumptions.retention_ratio
    return value.clip(lower_bound=0.0)
