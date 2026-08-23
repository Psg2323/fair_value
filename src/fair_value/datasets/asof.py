from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import polars as pl

FINANCIAL_KEY_RENAMES = {
    "period_end": "financial_period_end",
    "available_at": "financial_available_at",
    "receipt_no": "financial_receipt_no",
    "source": "financial_source",
}


def build_monthly_valuation_calendar(
    market_prices: pl.DataFrame,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    required = {"ticker", "trading_date", "close"}
    missing = required - set(market_prices.columns)
    if missing:
        raise ValueError(f"Missing market-price columns: {sorted(missing)}")

    frame = market_prices
    if start_date is not None:
        frame = frame.filter(pl.col("trading_date") >= start_date)
    if end_date is not None:
        frame = frame.filter(pl.col("trading_date") <= end_date)
    if frame.is_empty():
        raise ValueError("No market prices were available for the requested calendar")

    return (
        frame.sort(["ticker", "trading_date"])
        .with_columns(
            pl.col("trading_date").dt.year().alias("_year"),
            pl.col("trading_date").dt.month().alias("_month"),
        )
        .group_by(["ticker", "_year", "_month"], maintain_order=True)
        .agg(
            pl.col("trading_date").last().alias("valuation_date"),
            pl.col("close").last().cast(pl.Float64).alias("market_price"),
        )
        .drop(["_year", "_month"])
        .sort(["ticker", "valuation_date"])
    )


def build_valuation_asof_dataset(
    market_prices: pl.DataFrame,
    fundamentals: pl.DataFrame,
    economic_indicators: pl.DataFrame,
    domestic_cycle_features: pl.DataFrame,
    global_cycle_features: pl.DataFrame,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    indicator_ids: Iterable[str] | None = None,
) -> pl.DataFrame:
    """Build monthly inputs using only records available on each valuation date."""
    frame = build_monthly_valuation_calendar(market_prices, start_date, end_date)
    frame = _join_financial_frontier(frame, fundamentals)

    selected_indicators = (
        tuple(indicator_ids)
        if indicator_ids is not None
        else tuple(
            economic_indicators.get_column("indicator_id").unique(maintain_order=True).to_list()
        )
    )
    for indicator_id in selected_indicators:
        frame = _join_indicator_frontier(frame, economic_indicators, indicator_id)

    frame = _join_feature_frontier(
        frame,
        domestic_cycle_features,
        prefix="domestic_cycle_",
    )
    frame = _join_feature_frontier(
        frame,
        global_cycle_features,
        prefix="global_cycle_",
    )
    frame = frame.sort(["ticker", "valuation_date"])
    assert_point_in_time(frame)
    return frame


def assert_point_in_time(frame: pl.DataFrame) -> None:
    if "valuation_date" not in frame.columns:
        raise ValueError("valuation_date is required")
    availability_columns = [
        column_name for column_name in frame.columns if column_name.endswith("_available_at")
    ]
    violations = {
        column_name: frame.filter(
            pl.col(column_name).is_not_null() & (pl.col(column_name) > pl.col("valuation_date"))
        ).height
        for column_name in availability_columns
    }
    if invalid := {name: count for name, count in violations.items() if count > 0}:
        raise ValueError(f"Point-in-time availability violation: {invalid}")


def _join_financial_frontier(
    calendar: pl.DataFrame,
    fundamentals: pl.DataFrame,
) -> pl.DataFrame:
    required = {"ticker", "period_end", "available_at"}
    missing = required - set(fundamentals.columns)
    if missing:
        raise ValueError(f"Missing fundamental columns: {sorted(missing)}")

    financials = fundamentals.rename(FINANCIAL_KEY_RENAMES)
    frontier = _latest_period_frontier(
        financials,
        period_column="financial_period_end",
        available_column="financial_available_at",
        group_columns=("ticker",),
    )
    joined = calendar.sort(["ticker", "valuation_date"]).join_asof(
        frontier.sort(["ticker", "financial_available_at"]),
        left_on="valuation_date",
        right_on="financial_available_at",
        by="ticker",
        strategy="backward",
        check_sortedness=False,
    )
    return joined.filter(pl.col("financial_available_at").is_not_null())


def _join_indicator_frontier(
    calendar: pl.DataFrame,
    indicators: pl.DataFrame,
    indicator_id: str,
) -> pl.DataFrame:
    required = {"indicator_id", "period_end", "available_at", "value"}
    missing = required - set(indicators.columns)
    if missing:
        raise ValueError(f"Missing economic indicator columns: {sorted(missing)}")

    value_column = f"indicator_{indicator_id}"
    available_column = f"{value_column}_available_at"
    period_column = f"{value_column}_period_end"
    selected = (
        indicators.filter(pl.col("indicator_id") == indicator_id)
        .select("period_end", "available_at", "value")
        .rename(
            {
                "period_end": period_column,
                "available_at": available_column,
                "value": value_column,
            }
        )
    )
    if selected.is_empty():
        raise ValueError(f"Economic indicator is unavailable: {indicator_id}")
    frontier = _latest_period_frontier(
        selected,
        period_column=period_column,
        available_column=available_column,
    )
    return calendar.sort("valuation_date").join_asof(
        frontier.sort(available_column),
        left_on="valuation_date",
        right_on=available_column,
        strategy="backward",
    )


def _join_feature_frontier(
    calendar: pl.DataFrame,
    features: pl.DataFrame,
    prefix: str,
) -> pl.DataFrame:
    required = {"period_end", "available_at"}
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"Missing cycle feature columns: {sorted(missing)}")

    rename_map = {column_name: f"{prefix}{column_name}" for column_name in features.columns}
    selected = features.rename(rename_map)
    period_column = f"{prefix}period_end"
    available_column = f"{prefix}available_at"
    frontier = _latest_period_frontier(
        selected,
        period_column=period_column,
        available_column=available_column,
    )
    return calendar.sort("valuation_date").join_asof(
        frontier.sort(available_column),
        left_on="valuation_date",
        right_on=available_column,
        strategy="backward",
    )


def _latest_period_frontier(
    frame: pl.DataFrame,
    *,
    period_column: str,
    available_column: str,
    group_columns: tuple[str, ...] = (),
) -> pl.DataFrame:
    """Drop late-arriving older periods that must not replace newer observations."""
    sort_columns = [*group_columns, available_column, period_column]
    cumulative = (
        pl.col(period_column).cum_max().over(group_columns)
        if group_columns
        else pl.col(period_column).cum_max()
    )
    frontier = (
        frame.filter(pl.col(period_column).is_not_null() & pl.col(available_column).is_not_null())
        .sort(sort_columns)
        .with_columns(cumulative.alias("_latest_period"))
        .filter(pl.col(period_column) == pl.col("_latest_period"))
        .drop("_latest_period")
    )
    return frontier.unique(
        subset=[*group_columns, available_column],
        keep="last",
        maintain_order=True,
    )
